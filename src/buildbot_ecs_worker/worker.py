from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import socket

import boto3

from buildbot.worker import AbstractLatentWorker

from twisted.internet import defer, threads
from twisted.python import log


class ECSWorker(AbstractLatentWorker):
    def __init__(self, name, password, task_kwargs, container_name='buildbot', boto3_session=None, master_host=None,
                 build_wait_timeout=0, **kwargs):
        AbstractLatentWorker.__init__(self, name, password, build_wait_timeout=build_wait_timeout, **kwargs)
        self.master_host = master_host or socket.getfqdn()
        self.task_kwargs = task_kwargs
        self.container_name = container_name
        self.boto3_session = boto3_session or boto3.Session()
        self.ecs = self.boto3_session.client('ecs')

        assert 'cluster' in task_kwargs
        assert 'taskDefinition' in task_kwargs

    @defer.inlineCallbacks
    def start_instance(self, build):
        if self.instance is not None:
            log.err("Cannot start %s -- already active!", self.workername)
            defer.returnValue(False)
            return

        # setup the task kwargs for this specific instance
        # * copy the kwargs provided
        # * set count, startedBy & group
        # * add overrides to provide the required env vars
        task_kwargs = self.task_kwargs.copy()
        task_kwargs.update(dict(
            overrides=dict(
                containerOverrides=[
                    dict(
                        name=self.container_name,
                        environment=[
                            dict(name='BUILDMASTER', value=self.master_host),
                            dict(name='BUILDMASTER_PORT', value=str(self.registration.getPBPort())),
                            dict(name='WORKERNAME', value=self.name),
                            dict(name='WORKERPASS', value=self.password)
                        ]
                    )
                ]
            ),
            count=1,
            startedBy='buildbot',  # buildbot installation name?
            group='buildbot',  # buildbot installation name?
        ))

        # start the task
        resp = yield threads.deferToThread(self.ecs.run_task, **task_kwargs)

        if len(resp['failures']) > 0:
            log.err("Failed to start ECS task for %s: %s", self.workername, resp['failures'][0]['reason'])
            defer.returnValue(False)
            return

        self.instance = resp['tasks'][0]['taskArn']

        waiter = self.ecs.get_waiter('tasks_running')
        yield threads.deferToThread(waiter.wait, cluster=self.task_kwargs['cluster'], tasks=[self.instance])

        defer.returnValue(True)

    @defer.inlineCallbacks
    def stop_instance(self, fast=False):
        if self.instance is None:
            defer.returnValue(None)

        yield threads.deferToThread(self.ecs.stop_task, cluster=self.task_kwargs['cluster'], task=self.instance)

        if not fast:
            waiter = self.ecs.get_waiter('tasks_stopped')
            yield threads.deferToThread(waiter.wait, cluster=self.task_kwargs['cluster'], tasks=[self.instance])

        defer.returnValue(True)
