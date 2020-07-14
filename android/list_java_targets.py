#!/usr/bin/env python3
# Copyright 2020 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Lint as: python3
"""Prints out available java targets.

Examples:
# List GN target for bundles:
build/android/list_java_targets.py --output-directory out/Default \
--type android_app_bundle --gn-labels

# List all android targets with types:
build/android/list_java_targets.py --output-directory out/Default --print-types

# Build all apk targets:
build/android/list_java_targets.py --output-directory out/Default \
--type android_apk | xargs autoninja -C out/Default

# Show how many of each target type exist:
build/android/list_java_targets.py --output-directory out/Default --stats

"""

import argparse
import collections
import json
import logging
import os
import subprocess
import sys

_SRC_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..',
                                          '..'))
sys.path.append(os.path.join(_SRC_ROOT, 'build', 'android'))
from pylib import constants

_VALID_TYPES = (
    'android_apk',
    'android_app_bundle',
    'android_app_bundle_module',
    'android_assets',
    'android_resources',
    'dist_aar',
    'dist_jar',
    'group',
    'java_annotation_processor',
    'java_binary',
    'java_library',
    'junit_binary',
    'system_java_library',
)


def _run_ninja(output_dir, args):
  cmd = [
      'autoninja',
      '-C',
      output_dir,
  ]
  cmd.extend(args)
  logging.info('Running: %r', cmd)
  subprocess.run(cmd, check=True, stdout=sys.stderr)


def _query_for_build_config_targets(output_dir):
  # Query ninja rather than GN since it's faster.
  cmd = ['ninja', '-C', output_dir, '-t', 'targets']
  logging.info('Running: %r', cmd)
  ninja_output = subprocess.run(cmd,
                                check=True,
                                capture_output=True,
                                encoding='ascii').stdout
  ret = []
  SUFFIX = '__build_config_crbug_908819'
  SUFFIX_LEN = len(SUFFIX)
  for line in ninja_output.splitlines():
    ninja_target = line.rsplit(':', 1)[0]
    # Ignore root aliases by ensuring a : exists.
    if ':' in ninja_target and ninja_target.endswith(SUFFIX):
      ret.append('//' + ninja_target[:-SUFFIX_LEN])
  return ret


class _TargetEntry(object):
  _cached_entries = {}

  def __init__(self, gn_target):
    assert gn_target.startswith('//'), gn_target
    if ':' not in gn_target:
      gn_target = '%s:%s' % (gn_target, os.path.basename(gn_target))
    self.gn_target = gn_target
    self._build_config = None
    self._java_files = None
    self._all_entries = None
    self.android_test_entries = []

  @property
  def ninja_target(self):
    return self.gn_target[2:]

  @property
  def ninja_build_config_target(self):
    return self.ninja_target + '__build_config_crbug_908819'

  def build_config(self):
    """Reads and returns the project's .build_config JSON."""
    if not self._build_config:
      ninja_target = self.ninja_target
      # Support targets at the root level. e.g. //:foo
      if ninja_target[0] == ':':
        ninja_target = ninja_target[1:]
      subpath = ninja_target.replace(':', os.path.sep) + '.build_config'
      path = os.path.join('gen', subpath)
      with open(os.path.join(constants.GetOutDirectory(), path)) as jsonfile:
        self._build_config = json.load(jsonfile)
    return self._build_config

  def get_type(self):
    """Returns the target type from its .build_config."""
    return self.build_config()['deps_info']['type']


def main():
  parser = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument('--output-directory')
  parser.add_argument('--gn-labels',
                      action='store_true',
                      help='Print GN labels rather than ninja targets')
  parser.add_argument(
      '--nested',
      action='store_true',
      help='Do not convert nested targets to their top-level equivalents. '
      'E.g. Without this, foo_test__apk -> foo_test')
  parser.add_argument('--print-types',
                      action='store_true',
                      help='Print type of each target')
  parser.add_argument('--build-build-configs',
                      action='store_true',
                      help='Build all .build_config files.')
  parser.add_argument('--type',
                      action='append',
                      help='Restrict to targets of given type',
                      choices=_VALID_TYPES)
  parser.add_argument('--stats',
                      action='store_true',
                      help='Print counts of each target type.')
  parser.add_argument('-v', '--verbose', default=0, action='count')
  args = parser.parse_args()

  args.build_build_configs |= bool(args.type or args.print_types or args.stats)

  logging.basicConfig(level=logging.WARNING - (10 * args.verbose),
                      format='%(levelname).1s %(relativeCreated)6d %(message)s')

  if args.output_directory:
    constants.SetOutputDirectory(args.output_directory)
  constants.CheckOutputDirectory()
  output_dir = constants.GetOutDirectory()

  # Query ninja for all __build_config_crbug_908819 targets.
  targets = _query_for_build_config_targets(output_dir)
  entries = [_TargetEntry(t) for t in targets]

  if args.build_build_configs:
    logging.warning('Building %d .build_config files...', len(entries))
    _run_ninja(output_dir, [e.ninja_build_config_target for e in entries])

  if args.type:
    entries = [e for e in entries if e.get_type() in args.type]

  if args.stats:
    counts = collections.Counter(e.get_type() for e in entries)
    for entry_type, count in sorted(counts.items()):
      print('{}: {}'.format(entry_type, count))
  else:
    for e in entries:
      if args.gn_labels:
        to_print = e.gn_target
      else:
        to_print = e.ninja_target

      # Convert to top-level target
      if not args.nested:
        to_print = to_print.replace('__test_apk__apk', '').replace('__apk', '')

      if args.print_types:
        to_print = '{}: {}'.format(to_print, e.get_type())

      print(to_print)


if __name__ == '__main__':
  main()
