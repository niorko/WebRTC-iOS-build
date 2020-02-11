#!/usr/bin/env python
#
# Copyright 2018 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Deploys and runs a test package on a Fuchsia target."""

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time

from common_args import AddCommonArgs, ConfigureLogging, GetDeploymentTargetForArgs
from net_test_server import SetupTestServer
from run_package import RunPackage, RunPackageArgs

DEFAULT_TEST_CONCURRENCY = 4

TEST_RESULT_PATH = '/data/test_summary.json'
TEST_FILTER_PATH = '/data/test_filter.txt'

def main():
  parser = argparse.ArgumentParser()
  AddCommonArgs(parser)
  parser.add_argument('--gtest_filter',
                      help='GTest filter to use in place of any default.')
  parser.add_argument('--gtest_repeat',
                      help='GTest repeat value to use. This also disables the '
                           'test launcher timeout.')
  # TODO(crbug.com/1046861): Remove qemu-img-retries flag when qemu-img arm64
  # hang bug is fixed.
  parser.add_argument('--qemu-img-retries',
                      default=0,
                      type=int,
                      help='Number of times that the qemu-img command can be '
                           'retried.')
  parser.add_argument('--test-launcher-retry-limit',
                      help='Number of times that test suite will retry failing '
                           'tests. This is multiplicative with --gtest_repeat.')
  parser.add_argument('--gtest_break_on_failure', action='store_true',
                      default=False,
                      help='Should GTest break on failure; useful with '
                           '--gtest_repeat.')
  parser.add_argument('--single-process-tests', action='store_true',
                      default=False,
                      help='Runs the tests and the launcher in the same '
                           'process. Useful for debugging.')
  parser.add_argument('--test-launcher-batch-limit',
                      type=int,
                      help='Sets the limit of test batch to run in a single '
                      'process.')
  # --test-launcher-filter-file is specified relative to --output-directory,
  # so specifying type=os.path.* will break it.
  parser.add_argument('--test-launcher-filter-file',
                      default=None,
                      help='Override default filter file passed to target test '
                      'process. Set an empty path to disable filtering.')
  parser.add_argument('--test-launcher-jobs',
                      type=int,
                      help='Sets the number of parallel test jobs.')
  parser.add_argument('--test-launcher-summary-output',
                      help='Where the test launcher will output its json.')
  parser.add_argument('--enable-test-server', action='store_true',
                      default=False,
                      help='Enable Chrome test server spawner.')
  parser.add_argument('--test-launcher-bot-mode', action='store_true',
                      default=False,
                      help='Informs the TestLauncher to that it should enable '
                      'special allowances for running on a test bot.')
  parser.add_argument('--child-arg', action='append',
                      help='Arguments for the test process.')
  parser.add_argument('child_args', nargs='*',
                      help='Arguments for the test process.')
  args = parser.parse_args()
  ConfigureLogging(args)

  child_args = ['--test-launcher-retry-limit=0']
  if args.single_process_tests:
    child_args.append('--single-process-tests')
  if args.test_launcher_bot_mode:
    child_args.append('--test-launcher-bot-mode')
  if args.test_launcher_batch_limit:
    child_args.append('--test-launcher-batch-limit=%d' %
                       args.test_launcher_batch_limit)

  test_concurrency = args.test_launcher_jobs \
      if args.test_launcher_jobs else DEFAULT_TEST_CONCURRENCY
  child_args.append('--test-launcher-jobs=%d' % test_concurrency)

  if args.gtest_filter:
    child_args.append('--gtest_filter=' + args.gtest_filter)
  if args.gtest_repeat:
    child_args.append('--gtest_repeat=' + args.gtest_repeat)
    child_args.append('--test-launcher-timeout=-1')
  if args.test_launcher_retry_limit:
    child_args.append(
        '--test-launcher-retry-limit=' + args.test_launcher_retry_limit)
  if args.gtest_break_on_failure:
    child_args.append('--gtest_break_on_failure')
  if args.test_launcher_summary_output:
    child_args.append('--test-launcher-summary-output=' + TEST_RESULT_PATH)

  if args.child_arg:
    child_args.extend(args.child_arg)
  if args.child_args:
    child_args.extend(args.child_args)

  # KVM is required on x64 test bots.
  require_kvm = args.test_launcher_bot_mode and args.target_cpu == 'x64'

  with GetDeploymentTargetForArgs(args, require_kvm=require_kvm) as target:
    target.Start()

    if args.test_launcher_filter_file:
      target.PutFile(args.test_launcher_filter_file, TEST_FILTER_PATH,
                     for_package=args.package_name)
      child_args.append('--test-launcher-filter-file=' + TEST_FILTER_PATH)

    test_server = None
    if args.enable_test_server:
      test_server = SetupTestServer(target, test_concurrency,
                                    args.package_name)

    run_package_args = RunPackageArgs.FromCommonArgs(args)
    returncode = RunPackage(
        args.output_directory, target, args.package, args.package_name,
        child_args, run_package_args)

    if test_server:
      test_server.Stop()

    if args.test_launcher_summary_output:
      target.GetFile(TEST_RESULT_PATH, args.test_launcher_summary_output,
                     for_package=args.package_name)

    return returncode


if __name__ == '__main__':
  sys.exit(main())
