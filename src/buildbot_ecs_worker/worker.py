from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from buildbot.worker import AbstractLatentWorker


class ECSWorker(AbstractLatentWorker):
    def start_instance(self, build):
        raise RuntimeError("TODO")

    def stop_instance(self, fast=False):
        raise RuntimeError("TODO")
