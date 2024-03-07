#!/bin/env python3

from typing import Dict, List, Tuple

import sys

from argparse import ArgumentParser, Namespace
from collections import namedtuple
from random import choices
from shutil import rmtree, copy2, copystat
from subprocess import run
import string
import re

from datetime import datetime
from os.path import abspath, dirname, exists, isdir, join
from os.path import normpath, relpath, split
from os import getcwd, makedirs, rename, unlink, walk

from binaryornot.check import is_binary


## ----------------------------------------------------------------------------


# The default values of the arguments that control where the template comes
# from, what branch to use, and what path segment within it contains the setup
# script that should not be included in the final package.
DEFAULT_REPO_URL='git@github.com:OdatNurd/mkdocs-pkg-base.git'
DEFAULT_REPO_BRANCH='master'
DEFAULT_SETUP_PATH='setup/'

# The default version of Sublime to expand out into the template files if one
# is not provided. This is (at time of writing) the most recent stable build.
DEFAULT_SUBLIME_VERSION='4169'

# When preparing to generate the template, a tuple of this shape is used to
# determine what the source folder for the template is, what the destination
# is, and what files need to be copied in order to make the package.
#
# The template data also packs a dictionary that contains the names of the
# template variables that we support, and their values when they get expanded.
TemplateData = namedtuple('TemplateData', ['source', 'destination', 'files', 'variables'])

# When generating random suffixes for files, this is the list of characters
# that is drawn from.
KEY_CHARACTERS = string.ascii_uppercase + string.digits

## ----------------------------------------------------------------------------


def get_template_base() -> str:
    """
    Determine the base location where the package template lives, which is the
    parent folder of the folder in which the script that's currently running
    lives.

    Here we join the current directory with the path that was used to launch
    the script and a single uplevel directive (to go to the parent), and then
    normalize the whole thing.
    """
    return normpath(join(getcwd(), dirname(sys.argv[0]), '..'))


def get_template_variables(args: Namespace) -> Dict[str, str]:
    """
    Given a validated set of command line arguments, create and return back a
    dictionary whose keys are the names of template variables that we can
    expand, with values as appropriate.
    """
    variables = {
        'PackageName': args.package,
        'PackageTitle': args.title,
        'PackageURLSlug': args.url_slug,
        'Year': str(datetime.now().year),
        'SublimeVersion': args.sublime_version,
    }
    return variables


def execute_cmd(shell_cmd: str, working_dir: str) -> str:
    """
    Execute the given shell command within the provided working directory, and
    return back the data returned from stdout.

    If the task fails, an exception is raised.
    """
    p = run(shell_cmd, shell=True, cwd=working_dir, capture_output=True, encoding='utf-8')

    if p.returncode == 0:
        return p.stdout
    else:
        print(p.stderr)
        raise RuntimeError(f'task execution returned non-zero status')


def path_filter(args: Namespace, file_list: List[str]) -> List[str]:
    """
    Given a list of files, filter away any which do not constitute part of a
    template.

    This is intended to be used to filter a list of input files from file
    system scan or git calls to those which we know we should not include.
    """
    return filter(lambda n: n and (not args.skip or not n.startswith(args.skip)),
                  file_list)


def get_git_file_list(args: Namespace, repo_dir: str) -> List[str]:
    """
    Given a folder that is a git repository root, return back a list of all of
    the files in the folder other than those that are being explicitly ignored
    by git.

    In particular, this is the union of all tracked and untracked files.
    """
    result = []

    # Ask git to tell us which files are tracked and which are untracked and
    # also not ignored; filter each list and add any results to the ultimate
    # return.
    for git_args in ['ls-files', 'ls-files --others --exclude-standard']:
        files = execute_cmd(f"git {git_args}", repo_dir)
        result.extend(path_filter(args, files.split('\n')))

    return result


def get_folder_file_list(args: Namespace, base_dir: str) -> List[str]:
    """
    Given a folder that is the root the template source location, return a
    list of all files which should be copied from the template into the final
    output, or processed (if it is happening in place).

    This assumes that the folder given is not a git repository, in as much as
    it will not try to exclude the git control directory or any files that
    might exist but listed in the .gitignore file. For such folders, the
    get_git_file_list() function should be called instead.
    """
    result = []

    # Walk through the whole of the base directory looking for files. Paths
    # that fall out are absolute, so we need to make them relative to the base
    # folder (unless it's already the base)
    for (path, dirs, files) in walk(base_dir, followlinks=True):
        r_path = relpath(path, base_dir) if path != base_dir else ""
        for name in files:
            result.append(join(r_path, name))

    return list(path_filter(args, result))


def get_input_file_list(args: Namespace) -> TemplateData:
    """
    Based on the command line arguments provided, determine where the source of
    the template files is and
    """
    # Regardless of where we get the data from, the output is always a folder
    # named for the package in the current working directory.
    destination = abspath(join(getcwd(), args.package))

    # Get the list of template variables that we're going to expand out in our
    # templates. Some of these are based on command line arguments and some
    # are based on other static data.
    template_vars = get_template_variables(args)

    # If there is a local path that is the source of the template, then we
    # want to try and scan it's contents in order to get the list of files.
    if args.path:
        # Ensure that the base path we get is an absolute path
        base_dir = abspath(args.path)

        # Check to see if there's a .git folder in the path so we know how to
        # handle it.
        if isdir(join(base_dir, '.git')):
            return TemplateData(base_dir, destination, get_git_file_list(args, args.path), template_vars)

        return TemplateData(base_dir, destination, get_folder_file_list(args, args.path), template_vars)

    # We are trying to clone a specific branch from a repository to use as the
    # base; in this case, we will clone it directly into the location that we
    # want the output to be in.
    print(f'cloning {args.repo}:{args.branch} => {args.package}')
    execute_cmd(f"git clone -b {args.branch} --single-branch {args.repo} {args.package}", getcwd())

    # Gather the list of files from the cloned repository.
    files = get_git_file_list(args, destination)

    # Now, blow away the .git control folder in the root of the clone
    print(f'removing .git control folder')
    rmtree(join(destination, '.git'), ignore_errors=True)

    # If provided, the skip folder should also be removed now(since it should
    # be skipped).
    if args.skip:
        print(f'removing {args.skip}; asked to skip it')
        rmtree(join(destination, args.skip), ignore_errors=True)

    # A git clone operation happens in place, so the source and destination
    # will end up being the same.
    return TemplateData(destination, destination, files, template_vars)


## ----------------------------------------------------------------------------


def name_to_slug(input_name: str) -> str:
    """
    Given a textual name of a package, assumed to be in CamelCase, return back
    a version of the name where all of the text is lower case and everything is
    split at upper case characters.

    Any run of uppercase characters is only split once; so 'URL' becomes 'url'
    and not 'u-r-l'.
    """
    # If the name is all upper case, just convert it to lower case and return
    # directly.
    if input_name.isupper():
        return input_name.lower()

    # Build up the name character by character. Uppercase characters are
    # replaced with a dash and a lower case version of themselves, except for
    # the first one in the name, which should just be lower case.
    name = input_name[0].lower()
    last_upper = False
    for c in input_name[1:]:
        if c.isupper() and not last_upper:
            name += '-'
            name += c.lower()
        else:
            name += c
        last_upper = c.isupper()

    return name


def validate_arguments(parser: ArgumentParser, args: Namespace) -> Namespace:
    """
    Given a set of parsed command line arguments, verify that all values that
    are provided are valid for this operation; any arguments that are not
    valid cause the process to error out.

    This only does pre-job validation on the arguments, such as verifying that
    a local source folder exists; it does not verify if a git repo is valid,
    or has such a branch within it, etc.
    """
    # If a path was requested and also we were told to use the installation
    # path, generate an error
    if args.path and args.use_installed:
        parser.error(f'cannot use installed template; given explicit local folder')

    # If we were told to use the local installation path, put it into the path
    # argument as if the user specified it on their own.
    if args.use_installed:
        args.path = args.use_installed

    # We strictly require that there be an output package specified.
    if args.package is None:
        parser.error(f'no output package specified; cannot generate')

    # If the path specified for the package already exists in any form, we need
    # to bail.
    if exists(args.package):
        parser.error(f"cannot create package '{args.package}'; folder/file already exists")

    # If a local path was given, it must exist and be a folder so we can pluck
    # files from within it.
    if args.path is not None and not isdir(args.path):
        parser.error(f"local template source '{args.path}' does not exist or is not a folder")

    # If we are supposed to skip tossing out the setup folder, then remove the
    # skip folder.
    if args.no_skip:
        args.skip = None

    # If there is a skip folder, make sure that it's got a trailing path
    # separator on it.
    if args.skip:
        args.skip = join(args.skip, '')

    # If there is no title specified, then the title will have the same
    # value as the package name.
    if not args.title:
        args.title = args.package

    # If there is no URL slug, create a version that's based on the name of the
    # package converted to lower case and with words separated by dashes.
    if not args.url_slug:
        args.url_slug = name_to_slug(args.package)

    return args


def parse_cmd_line() -> Namespace:
    """
    Process command line arguments in order to determine what sort of operation
    is desired, and how to carry out the new package command.

    The return value is the parsed and validated values of the command line
    arguments.
    """
    parser = ArgumentParser(
        description="Scaffold out a new Sublime Text package from a template"
    )

    # Set up arguments that control where our input comes from
    src = parser.add_argument_group(
        title="Template Source",
        description="""Source of the underlying template data. The template can
            contain a single optional path that contains the template setup
            tools, which will be skipped when using the template."""
    )
    src.add_argument('--git', '-g',
                     dest='repo',
                     help=f'Obtain the template by cloning a git repository [Default: {DEFAULT_REPO_URL}]',
                     metavar='repo_url',
                     default=DEFAULT_REPO_URL)
    src.add_argument('--branch', '-b',
                     help=f'Branch to use in the given repository (infers --git) [Default: {DEFAULT_REPO_BRANCH}]',
                     metavar='branch',
                     default=DEFAULT_REPO_BRANCH)
    src.add_argument('--local', '-l',
                     dest='path',
                     help='Use template rooted in a local folder',
                     metavar='path')
    src.add_argument('--use-installed', '-i',
                     help='Use the version of the template from the script installation folder',
                     const=get_template_base(),
                     action='store_const')
    src.add_argument('--skip', '-s',
                     help=f'Relative path within the template that contains setup information [Default: {DEFAULT_SETUP_PATH}]',
                     metavar='path',
                     default=DEFAULT_SETUP_PATH)

    dest = parser.add_argument_group(
        title="Package Output",
        description="Options that control the generated output package"
    )
    dest.add_argument('--package', '-p',
                      help='Name of the package to create from the template',
                      metavar='PackageName')
    dest.add_argument('--require-sublime', '-r',
                      dest='sublime_version',
                      help=f'Minimum version of Sublime required for this package [Default: {DEFAULT_SUBLIME_VERSION}]',
                      default=DEFAULT_SUBLIME_VERSION,
                      metavar='build_num')
    dest.add_argument('--title', '-t',
                      help='Descriptive name of the destination package [Default: PackageName]',
                      metavar='PackageTitle')
    dest.add_argument('--slug', '-u',
                      dest='url_slug',
                      help='The URL slug for the subdomain of the project [Default: package-name]',
                      metavar='url-slug')
    dest.add_argument('--no-skip', '-n',
                      help="Disable skipping the configured skip folder when copying the template",
                      default=False,
                      action='store_true')

    # Parse the arguments and do validation
    return validate_arguments(parser, parser.parse_args())


## ----------------------------------------------------------------------------


def expand_template_contents(template: TemplateData, src: str, dst: str) -> None:
    """
    Given a template data structure and a source and destination file where the
    source file is known to be text, copy the source to the destination,
    expanding out any template variables in the content along the way.

    This expands out the variables from the template data in the file content
    as the file is copied.
    """
    def expand(match: re.Match) -> str:
        return template.variables.get(match.group(1), f'{{{{{match.group(1)}}}}}')

    with open(src, 'r', encoding='utf-8') as input_file:
        # Get the entire file content into memory
        raw = input_file.read()

        # Replace everything that looks like a variable expansion; if the
        # variable is not known, the expansion replaces it with itself so that
        # it does not get clobbered.
        cooked = re.sub(r"{{([^}]+)}}", lambda match: expand(match), raw)

        with open(dst, 'w', encoding='utf-8') as output_file:
            output_file.write(cooked)

    # Get the mode on the source file and ensure that it's applied to the
    # destination file.
    copystat(src, dst)


def handle_template_file(template: TemplateData, src: str, dst: str) -> None:
    """
    Given a template data structure and a source and destination file,
    determine what kind of file the source is and either copy it directly or
    copy it while expanding template variables within.

    When the source and destination file (not counting the path) are the same
    file, the data is copied and transformed, and the job is considered
    complete.

    If the source and destination files have different file names, then the
    file is copied and transformed into the new file, and then the source file
    is deleted and the destination file is renamed to replace it.

    The function is smart enough to not bother creating interim temporary files
    for files that don't need one (e.g. when handling a binary file that is
    already in the correct location).
    """
    src_path, src_file = split(src)
    dst_path, dst_file = split(dst)

    # For display purposes, get the name of the output file relative to the
    # folder that we're outputting it top.
    rel_name = relpath(join(dst_path, src_file), template.destination)

    # If the source and destination folders are not the same, then make sure
    # that the destination folder exists so that we can copy files there.
    if src_path != dst_path:
        makedirs(dst_path, exist_ok=True)

    # If the source file is binary, then we just need to copy the data over
    # without performing any expansions on it. The copy attempts to keep the
    # same metadata as the source where possible.
    if is_binary(src):
        # Do nothing if the filenames are different; we're working with an in
        # place template expansion via git in that case; nothing to do.
        if src_file != dst_file:
            return print(f'SKIP: {rel_name} [Binary]')

        print(f'Copy: {rel_name}')
        return copy2(src, dst)

    # The file is not binary, so we need to expand template variables within
    # the content as we copy it.
    print(f'Xpnd: {rel_name}')
    expand_template_contents(template, src, dst)

    # If the source and destination file have different names, then we need to
    # delete the source file and rename the destination to be that name; this
    # particular situation only happens when we are modifying files in place,
    # such as when we do a clone.
    if src_file != dst_file:
        unlink(src)
        rename(dst, src)


def expand_template(args: Namespace, template: TemplateData) -> None:
    """
    Do the work of actually expanding the template mentioned in the template
    data. This can both copy files from the source to the destination as well
    as editing files "in place" should the source and destination be the same
    folder (such as when we got the source via a git clone).
    """
    print(f'\nGenerating template package')
    print(f'Template Path: {template.source}')
    print(f' Package Path: {template.destination}\n')

    for file in template.files:
        # Get fully qualified names for both files
        src_file = join(template.source, file)
        dst_file = join(template.destination, file)

        # If the source and destination are the same file, then we need to
        # append a random tag onto the destination, since we will need to edit
        # it in place.
        if src_file == dst_file:
            dst_file = f'{dst_file}-{"".join(choices(KEY_CHARACTERS, k=12))}'

        # Copy the file over, doing any expansions needed
        handle_template_file(template, src_file, dst_file)


## ----------------------------------------------------------------------------


# Grab and validate all command line arguments; execution stops here if
# anything appears to be amiss.
args = parse_cmd_line()

# Display what it is that we're doing.
print('-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-')
print(f' src: {args.path if args.path else f"{args.repo}:{args.branch}"}')
print(f' pkg: {args.package}')
if args.skip:
    print(f'skip: {args.skip}')
print('-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-')

try:
    # Determine the input and output folder paths and the list of files that
    # make up the template.
    #
    # If the command line tells us to use git, this will attempt to create a
    # folder directly by doing a clone of the repository.
    tpl_setup = get_input_file_list(args)

    # Expand the template out now
    expand_template(args, tpl_setup)

except:
    print('error encountered; cleaning up')
    rmtree(args.package, ignore_errors=True)
    raise
