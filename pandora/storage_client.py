#!/usr/bin/env python3

from __future__ import annotations

import operator

from datetime import datetime
from typing import overload

from redis import ConnectionPool, Redis

from .default import get_config


class Storage():

    _instance = None

    def __new__(cls) -> Storage:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._redis_pool_storage: ConnectionPool = ConnectionPool(
                host=get_config('generic', 'storage_db_hostname'),
                port=get_config('generic', 'storage_db_port'),
                decode_responses=True)
        return cls._instance

    @property
    def storage(self) -> Redis:  # type: ignore[type-arg]
        return Redis(connection_pool=self._redis_pool_storage)

    # #### User ####

    def get_user(self, user_id: str) -> dict[str, str] | None:
        return self.storage.hgetall(f'users:{user_id}')

    def set_user(self, user: dict[str, str]) -> None:
        self.storage.hmset(f'users:{user["session_id"]}', user)  # type: ignore[arg-type]
        self.storage.expire(f'users:{user["session_id"]}', get_config('generic', 'session_expire'))
        self.storage.sadd('users', user["session_id"])

    def get_users(self) -> list[dict[str, str]]:
        users = []
        to_pop = []
        for session_id in self.storage.smembers('users'):
            user = self.storage.hgetall(f'users:{session_id}')
            if user:
                users.append(user)
            else:
                # Session expired
                to_pop.append(session_id)
        if to_pop:
            self.storage.srem('users', *to_pop)
        users.sort(key=operator.itemgetter('last_seen'), reverse=True)
        return users

    def del_users(self) -> None:
        to_delete = [f'users:{key}' for key in self.storage.smembers('users')]
        to_delete.append('users')
        self.storage.delete(*to_delete)

    # ##############

    # #### Role ####

    def get_role(self, role_name: str) -> dict[str, str]:
        return self.storage.hgetall(f'roles:{role_name}')

    def get_roles(self) -> list[dict[str, str]]:
        roles = []
        for role_name in sorted(list(self.storage.smembers('roles'))):
            roles.append(self.get_role(role_name))
        return roles

    def set_role(self, role: dict[str, str]) -> None:
        self.storage.hmset(f'roles:{role["name"]}', role)  # type: ignore[arg-type]
        self.storage.sadd('roles', role["name"])

    def has_roles(self) -> bool:
        return bool(self.storage.exists('roles'))

    # ##############

    # #### Observable ####

    def set_observable(self, observable: dict[str, str]) -> None:
        timestamp = datetime.fromisoformat(observable['last_seen']).timestamp()
        identifier = f'{observable["sha256"]}-{observable["observable_type"]}'

        self.storage.hmset(f'observables:{identifier}', observable)  # type: ignore[arg-type]
        if self.storage.hexists(f'observables:{identifier}', 'warninglist'):
            # Clear old way to store WLs
            self.storage.hdel(f'observables:{identifier}', 'warninglist')
        # TODO: use that in search page for observables.
        # Note: scan doesn't return the entries in any order, so we need to paginate manually
        self.storage.zadd('observables', {identifier: timestamp})

    @overload
    def get_observable(self, sha256: str, observable_type: str) -> dict[str, str] | None:
        ...

    @overload
    def get_observable(self, identifier: str) -> dict[str, str] | None:
        ...

    def get_observable(self, sha256: str | None=None,  # type: ignore[misc]
                       observable_type: str | None =None,
                       identifier: str | None=None) -> dict[str, str] | None:
        if not identifier:
            identifier = f'{sha256}-{observable_type}'
        return self.storage.hgetall(f'observables:{identifier}')

    def get_task_observables(self, task_uuid: str) -> list[dict[str, str]]:
        observables = []
        for identifier in self.storage.smembers(f'{task_uuid}:observables'):
            observable = self.get_observable(identifier=identifier)
            if observable:
                observables.append(observable)
        return observables

    def add_task_observable(self, task_uuid: str, sha256: str, observable_type: str) -> None:
        self.storage.sadd(f'{task_uuid}:observables', f'{sha256}-{observable_type}')

    # #### Observables lists ####

    def get_suspicious_observables(self) -> dict[str, str]:
        return self.storage.hgetall('suspicious_observables')

    def add_suspicious_observable(self, observable: str, observable_type: str) -> None:
        self.storage.hset('suspicious_observables', observable.strip(), observable_type.strip())

    def delete_suspicious_observable(self, observable: str) -> None:
        self.storage.hdel('suspicious_observables', observable.strip())

    def get_legitimate_observables(self) -> dict[str, str]:
        return self.storage.hgetall('legitimate_observables')

    def add_legitimate_observable(self, observable: str, observable_type: str) -> None:
        self.storage.hset('legitimate_observables', observable.strip(), observable_type.strip())

    def delete_legitimate_observable(self, observable: str) -> None:
        self.storage.hdel('legitimate_observables', observable.strip())

    # ##############

    # #### File ####

    def get_file(self, file_id: str) -> dict[str, str]:
        return self.storage.hgetall(f'files:{file_id}')

    def set_file(self, file_details: dict[str, str | int]) -> None:
        self.storage.hmset(f'files:{file_details["uuid"]}', file_details)  # type: ignore[arg-type]
        self.storage.sadd('files', file_details["uuid"])

    def get_files(self) -> list[dict[str, str]]:
        files = []
        for uuid in self.storage.smembers('files'):
            files.append(self.get_file(uuid))
        return files

    # ##############

    # #### Task ####

    def get_task(self, task_id: str) -> dict[str, str]:
        return self.storage.hgetall(f'tasks:{task_id}')

    def set_task(self, task: dict[str, str]) -> None:
        timestamp = datetime.fromisoformat(task['save_date']).timestamp()
        self.storage.hmset(f'tasks:{task["uuid"]}', task)  # type: ignore[arg-type]
        self.storage.zadd('tasks', {task["uuid"]: timestamp})

    def get_tasks(self, *, first_date: str | float=0, last_date: str | float='+Inf') -> list[dict[str, str]]:
        tasks = []
        for uuid in self.storage.zrevrangebyscore('tasks', min=first_date, max=last_date):
            tasks.append(self.get_task(uuid))
        tasks.sort(key=operator.itemgetter('save_date'), reverse=True)
        return tasks

    def count_tasks(self, *, first_date: str | float=0, last_date: str | float='+Inf') -> int:
        return self.storage.zcount('tasks', min=first_date, max=last_date)

    def add_extracted_reference(self, parent_task_uuid: str, extracted_task_uuid: str) -> None:
        self.storage.sadd(f'tasks:{parent_task_uuid}:extracted', extracted_task_uuid)

    def get_extracted_references(self, task_id: str) -> set[str]:
        return self.storage.smembers(f'tasks:{task_id}:extracted')

    # ##############

    # #### Report ####

    def get_report(self, task_uuid: str, worker_name: str) -> dict[str, str]:
        return self.storage.hgetall(f'reports:{task_uuid}-{worker_name}')

    def set_report(self, report: dict[str, str]) -> None:
        self.storage.hmset(f'reports:{report["task_uuid"]}-{report["worker_name"]}', report)  # type: ignore[arg-type]
        # In case the status of the task was set, drop it
        self.storage.hdel(f'tasks:{report["task_uuid"]}', 'status')
