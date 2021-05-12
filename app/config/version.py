#!/usr/bin/env python
import subprocess

# Note that this file is overwritten during the build
# process by either the git tag of the commit
# (see Dockerfile for details)

# By default we expect to find a leightweight tag in
# the history
# This has the form 'v[0-9]+\.[0-9]+\.[0-9]+-beta.[0-9]' if
# the tag is directly related to the commit or has an additional
# suffix 'v[0-9]+\.[0-9]+\.[0-9]+-beta.[0-9]-[0-9]+-gHASH' denoting
# the 'distance' to the latest tag
with subprocess.Popen(["git", "describe", "--tags"], stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE) as proc:
    stdout, stderr = proc.communicate()
GIT_VERSION = stdout.decode('utf-8').strip()
if GIT_VERSION == '':
    # If theres no git tag found in the history we simply use the short
    # version of the latest git commit hash
    with subprocess.Popen(["git", "rev-parse", "--short", "HEAD"],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE) as proc:
        stdout, stderr = proc.communicate()
    APP_VERSION = f"v_{stdout.decode('utf-8').strip()}"
else:
    APP_VERSION = GIT_VERSION
