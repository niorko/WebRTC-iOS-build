#!/usr/bin/env vpython3
#
# Copyright 2021 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
'''Implements Chrome-Fuchsia package binary size differ.'''

import argparse
import collections
import copy
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

from common import GetHostToolPathFromPlatform, GetHostArchFromPlatform
from common import SDK_ROOT, DIR_SOURCE_ROOT
from binary_sizes import ReadPackageSizesJson
from binary_sizes import PACKAGES_SIZES_FILE

_MAX_DELTA_BYTES = 12 * 1024  # 12 KiB
_TRYBOT_DOC = 'https://chromium.googlesource.com/chromium/src/+/main/docs/speed/binary_size/fuchsia_binary_size_trybot.md'


def ComputePackageDiffs(before_sizes_file, after_sizes_file):
  '''Computes difference between after and before diff, for each package.'''
  before_sizes = ReadPackageSizesJson(before_sizes_file)
  after_sizes = ReadPackageSizesJson(after_sizes_file)

  assert before_sizes.keys() == after_sizes.keys(), (
      'Package files cannot'
      ' be compared with different packages: '
      '%s vs %s' % (before_sizes.keys(), after_sizes.keys()))

  growth = {'compressed': {}, 'uncompressed': {}}
  status_code = 0
  summary = ''
  for package_name in before_sizes:
    growth['compressed'][package_name] = (after_sizes[package_name].compressed -
                                          before_sizes[package_name].compressed)
    growth['uncompressed'][package_name] = (
        after_sizes[package_name].uncompressed -
        before_sizes[package_name].uncompressed)
    if growth['compressed'][package_name] >= _MAX_DELTA_BYTES:
      if status_code == 1 and not summary:
        summary = 'Size check failed! The following package(s) are affected:\n'
      status_code = 1
      summary += ('- %s grew by %d bytes\n' %
                  (package_name, growth['compressed'][package_name]))

  growth['status_code'] = status_code
  summary += ('\nSee the following document for more information about'
              ' this trybot:\n%s' % _TRYBOT_DOC)
  growth['summary'] = summary.replace('\n', '<br>')

  # TODO(crbug.com/1266085): Investigate using these fields.
  growth['archive_filenames'] = []
  growth['links'] = []
  return growth


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '--before-dir',
      type=os.path.realpath,
      required=True,
      help='Location of the build without the patch',
  )
  parser.add_argument(
      '--after-dir',
      type=os.path.realpath,
      required=True,
      help='Location of the build with the patch',
  )
  parser.add_argument(
      '--results-path',
      type=os.path.realpath,
      required=True,
      help='Output path for the trybot result .json file',
  )
  parser.add_argument('--verbose',
                      '-v',
                      action='store_true',
                      help='Enable verbose output')
  args = parser.parse_args()

  if args.verbose:
    print('Fuchsia binary sizes')
    print('Working directory', os.getcwd())
    print('Args:')
    for var in vars(args):
      print('  {}: {}'.format(var, getattr(args, var) or ''))

  if not os.path.isdir(args.before_dir) or not os.path.isdir(args.after_dir):
    raise Exception('Could not find build output directory "%s" or "%s".' %
                    (args.before_dir, args.after_dir))

  test_name = 'sizes'
  before_sizes_file = os.path.join(args.before_dir, test_name,
                                   PACKAGES_SIZES_FILE)
  after_sizes_file = os.path.join(args.after_dir, test_name,
                                  PACKAGES_SIZES_FILE)
  if not os.path.isfile(before_sizes_file):
    raise Exception('Could not find before sizes file: "%s"' %
                    (before_sizes_file))

  if not os.path.isfile(after_sizes_file):
    raise Exception('Could not find after sizes file: "%s"' %
                    (after_sizes_file))

  test_completed = False
  try:
    growth = ComputePackageDiffs(before_sizes_file, after_sizes_file)
    test_completed = True
    with open(args.results_path, 'wt') as results_file:
      json.dump(growth, results_file)
  except:
    _, value, trace = sys.exc_info()
    traceback.print_tb(trace)
    print(str(value))
  finally:
    return 0 if test_completed else 1


if __name__ == '__main__':
  sys.exit(main())
