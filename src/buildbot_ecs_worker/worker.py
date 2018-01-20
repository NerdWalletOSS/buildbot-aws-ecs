from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import socket

import boto3

from buildbot import config
from buildbot.worker import AbstractLatentWorker

from twisted.internet import defer, threads
from twisted.python import log


class ECSWorker(AbstractLatentWorker):
    """A latent worker that runs in AWS ECS tasks.

    The ECS task definition must already exist, and is to be specified in the run_task_kwargs parameter.

    The image that is run inside the task definition should function like the default `buildbot/buildbot-worker`_ image,
    such that when run it will use the environment variables ``BUILDMASTER``, ``BUILDMASTER_PORT`` (if available),
    ``WORKERNAME``, and ``WORKERPASS`` to connect back to the master.

    For the purposes of supplying the environment variables as overrides it is expected that a container inside the task
    definition is called buildbot.  If it is called something different you can use the container_name parameter when
    creating the worker.

    Here is a minimal setup of a task definition using the ``aws`` CLI tool.

    ``my-buildbot.json``:

    .. code-block:: json

        {
          "containerDefinitions": [
            {
              "name": "buildbot",
              "image": "buildbot/buildbot-worker",
              "cpu": 1024,
              "memory": 2048,
              "essential": true
            }
          ],
          "family": "my-buildbot"
        }


    .. code-block:: bash

        aws ecs register-task-definition --cli-input-json file://./my-buildbot.json

    .. _buildbot/buildbot-worker: https://hub.docker.com/r/buildbot/buildbot-worker/

    :param str name: The worker name
    :param dict run_task_kwargs: The kwargs to use when running tasks, requires at least ``cluster`` and
                                 ``taskDefinition``.  See the boto3 documentation for a list of all options:
                                 http://boto3.readthedocs.io/en/latest/reference/services/ecs.html#ECS.Client.run_task
    :param str container_name: The container name used in the task that we will supply environment variables to
    :param boto3.Session boto_session: A boto3 Session object to use when creating the ecs client, if required
    :param str master_host: If specified can be ``hostname`` or ``hostname:port``, otherwise defaults to the master fdqn
    :param int build_wait_timeout: Defaults to 0 for ECS tasks so each build runs in a fresh container
    """

    def checkConfig(self, name, run_task_kwargs, container_name='buildbot', boto3_session=None, master_host=None,
                    build_wait_timeout=0, **kwargs):
        if 'cluster' not in run_task_kwargs:
            config.error("You must specify a cluster in the ECSWorker run_task_kwargs")

        if 'taskDefinition' not in run_task_kwargs:
            config.error("You must specify a taskDefinition in the ECSWorker run_task_kwargs")

        return AbstractLatentWorker.checkConfig(self, name, password=None, build_wait_timeout=build_wait_timeout,
                                                **kwargs)

    def reconfigService(self, name, run_task_kwargs, container_name='buildbot', boto3_session=None, master_host=None,
                        build_wait_timeout=0, **kwargs):
        # create a random password for this worker
        password = kwargs.pop('password', self.getRandomPass())

        self.master_host = master_host or socket.getfqdn()
        self.run_task_kwargs = run_task_kwargs
        self.container_name = container_name
        self.boto3_session = boto3_session or boto3.Session()
        self.ecs = self.boto3_session.client('ecs')
        self.task_arn = None

        return AbstractLatentWorker.reconfigService(self, name, password=password,
                                                    build_wait_timeout=build_wait_timeout, **kwargs)

    @defer.inlineCallbacks
    def start_instance(self, build):
        if self.task_arn is not None:
            log.err("Cannot start %s -- already active!" % (self.workername,))
            defer.returnValue(False)
            return

        # construct the environment
        host_parts = self.master_host.split(':')
        environment = [
            dict(name='WORKERNAME', value=self.name),
            dict(name='WORKERPASS', value=self.password),
            dict(name='BUILDMASTER', value=host_parts[0]),
        ]

        if len(host_parts) > 1:
            environment.extend([
                dict(name='BUILDMASTER_PORT', value=host_parts[1]),
            ])
        elif self.registration:
            environment.extend([
                dict(name='BUILDMASTER_PORT', value=str(self.registration.getPBPort()))
            ])

        run_task_kwargs = self.run_task_kwargs.copy()
        run_task_kwargs.update(dict(
            overrides=dict(
                containerOverrides=[
                    dict(
                        name=self.container_name,
                        environment=environment
                    )
                ]
            ),
            count=1,
            startedBy='buildbot',  # buildbot installation name?
            group='buildbot',  # buildbot installation name?
        ))

        # start the task
        log.msg("Running task definition %s for worker %s..." % (self.run_task_kwargs['taskDefinition'],
                                                                 self.workername))
        resp = yield threads.deferToThread(self.ecs.run_task, **run_task_kwargs)

        if len(resp['failures']) > 0:
            log.err("Failed to start ECS task for %s: %s" % (self.workername, resp['failures'][0]['reason']))
            defer.returnValue(False)
            return

        self.task_arn = resp['tasks'][0]['taskArn']

        log.msg("Started task %s for worker %s!  Waiting for RUNNING state..." % (self.task_arn, self.workername))

        # wait for the task to enter running state
        waiter = self.ecs.get_waiter('tasks_running')
        yield threads.deferToThread(waiter.wait, cluster=self.run_task_kwargs['cluster'], tasks=[self.task_arn])

        log.msg("Task %s for worker %s is now running!" % (self.task_arn, self.workername))

        defer.returnValue(True)

    @defer.inlineCallbacks
    def stop_instance(self, fast=False):
        if self.task_arn is None:
            defer.returnValue(None)

        log.msg("Stopping task %s for worker %s..." % (self.task_arn, self.workername))
        yield threads.deferToThread(self.ecs.stop_task, cluster=self.run_task_kwargs['cluster'], task=self.task_arn)

        if not fast:
            log.msg("Waiting for task %s for worker %s to reach STOPPED state..." % (self.task_arn, self.workername))
            waiter = self.ecs.get_waiter('tasks_stopped')
            yield threads.deferToThread(waiter.wait, cluster=self.run_task_kwargs['cluster'], tasks=[self.task_arn])
            log.msg("Task %s for worker %s is now stopped!" % (self.task_arn, self.workername))

        self.task_arn = None
        defer.returnValue(True)
