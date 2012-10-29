#!/usr/bin/python
# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2012 reddit
# Inc. All Rights Reserved.
###############################################################################
"""Clean up the static files S3 bucket.

This script removes static files that are no longer used from the S3 bucket.

"""

import datetime
import itertools
import os
import subprocess

from pylons import g

from r2.lib.db.operators import desc
from r2.lib.plugin import PluginLoader
from r2.lib.utils import fetch_things2
from r2.lib.utils import read_static_file_config
from r2.models import Subreddit
import r2


def get_mature_files_on_s3(bucket):
    """Enumerate files currently on S3 that are older than one day."""

    minimum_age = datetime.timedelta(days=1)
    minimum_birthdate = datetime.datetime.utcnow() - minimum_age

    remote_files = {}
    for key in bucket.list():
        last_modified = datetime.datetime.strptime(key.last_modified,
                                                   "%Y-%m-%dT%H:%M:%S.%fZ")
        if last_modified < minimum_birthdate:
            remote_files[key.name] = key
    return remote_files


def _get_repo_source_static_files(package_root):
    static_file_root = os.path.join(package_root, "public", "static")
    old_root = os.getcwd()

    try:
        os.chdir(static_file_root)
    except OSError:
        # this repo has no static files!
        return

    try:
        git_files_string = subprocess.check_output([
            "git", "ls-tree", "-r", "--name-only", "HEAD", static_file_root])
        git_files = git_files_string.splitlines()
        prefix = os.path.commonprefix(git_files)
        for path in git_files:
            filename = path[len(prefix):]
            yield filename
    finally:
        os.chdir(old_root)


def get_source_static_files(plugins):
    """List all static files that are committed to the git repository."""

    package_root = os.path.dirname(r2.__file__)
    # oh "yield from", how i wish i had thee.
    for filename in _get_repo_source_static_files(package_root):
        yield filename

    for plugin in plugins:
        for filename in _get_repo_source_static_files(plugin.path):
            yield filename


def get_generated_static_files():
    """List all static files that are generated by the build process."""
    PluginLoader()  # ensure all the plugins put their statics in
    for filename, mangled in g.static_names.iteritems():
        yield filename
        yield mangled

        _, ext = os.path.splitext(filename)
        if ext in (".css", ".js"):
            yield filename + ".gzip"
            yield mangled + ".gzip"


def get_live_subreddit_stylesheets():
    """List all currently visible subreddit stylesheet files."""
    subreddits = Subreddit._query(sort=desc("_date"))
    for sr in fetch_things2(subreddits):
        if sr.stylesheet_is_static:
            yield sr.static_stylesheet_name


def clean_static_files(config_file):
    bucket, config = read_static_file_config(config_file)
    ignored_prefixes = tuple(p.strip() for p in
                             config["ignored_prefixes"].split(","))

    plugins = PluginLoader()
    reachable_files = itertools.chain(
        get_source_static_files(plugins),
        get_generated_static_files(),
        get_live_subreddit_stylesheets(),
    )

    condemned_files = get_mature_files_on_s3(bucket)
    for reachable_file in reachable_files:
        if reachable_file in condemned_files:
            del condemned_files[reachable_file]

    for filename, key in condemned_files.iteritems():
        if not filename.startswith(ignored_prefixes):
            key.delete()
