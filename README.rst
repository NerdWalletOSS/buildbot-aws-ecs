Buildbot Latent Worker for AWS ECS
==================================

This is a `Buildbot`_ plugin that provides a `latent worker`_ that leverages the `AWS ECS`_ service to run builds.

Each build is run in its own ECS task, such that each build is run in a pristine environment -- unless you share a
volume between builds.

.. _Buildbot: http://buildbot.net/
.. _latent worker: https://docs.buildbot.net/current/manual/cfg-workers.html#latent-workers
.. _AWS ECS: https://aws.amazon.com/ecs/
