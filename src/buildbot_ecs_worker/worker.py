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

    @defer.inlineCallbacks
    def start_instance(self, build):
        if self.instance is not None:
            log.msg("Cannot start %s -- already active!", self.workername)
            defer.returnValue(False)

        yield threads.deferToThread(self._start_instance)

    @defer.inlineCallbacks
    def stop_instance(self, fast=False):
        if self.instance is None:
            defer.returnValue(None)

    def _start_instance(self):
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
            startedBy='buildbot', # buildbot installation name?
            group='buildbot', # buildbot installation name?
        ))

        # start the task
        resp = self.ecs.run_task(**task_kwargs)
