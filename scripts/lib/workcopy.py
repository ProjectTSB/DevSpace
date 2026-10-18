"""Read-only Git queries about one working copy, shared by the checks under scripts/.

A working copy opened through GIT_DIR and GIT_WORK_TREE from another environment is
supported; `git_problem` tells when git would read some other tree or repository.
"""
import os
import re
import subprocess
import sys
from pathlib import Path


class GitFailure(Exception):
    """A Git query that had to answer, such as the list of changes, failed."""


def git_output(root, *arguments, strip=True, required=False):
    """Query Git read-only; `strip=False` keeps the leading status characters.

    A failed query gives an empty string, or raises GitFailure when `required` is set:
    for a list of changes or files, an empty answer would read as "nothing to check".
    """
    # Without optional locks a query such as status does not refresh and rewrite the index,
    # which a parallel session may be writing. Git writes UTF-8 whatever the OS encoding is
    # (cp932 on Japanese Windows); a byte that is not UTF-8 survives as a surrogate.
    # Pathspec modes from the environment, such as GIT_LITERAL_PATHSPECS, would turn a
    # pattern like `*.mcfunction` into a literal name and match nothing, and GIT_DIFF_OPTS
    # overrides `-U0` with context lines that would read as changed.
    environment = {key: value for key, value in os.environ.items()
                   if not (key.startswith('GIT_') and key.endswith('_PATHSPECS'))
                   and key != 'GIT_DIFF_OPTS'}
    try:
        result = subprocess.run(('git', '--no-optional-locks', '-C', str(root)) + arguments,
                                capture_output=True, encoding='utf-8', errors='surrogateescape',
                                check=False, env=environment)
    except OSError as error:
        if required:
            raise GitFailure(str(error)) from error
        return ''
    # On Windows a decoding error is raised in a reader thread and leaves stdout as None.
    if result.returncode != 0 or result.stdout is None:
        if required:
            raise GitFailure((result.stderr or '出力を読めない').strip().split('\n')[0])
        return ''
    return result.stdout.strip() if strip else result.stdout


def utf8_console():
    """Write UTF-8 to stdout and stderr even where the console encoding is cp932."""
    # A replaced stream, such as a test's StringIO, has no encoding to change.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')


def git_problem(root):
    """Explain why git does not read this working copy as itself, or return None."""
    root = Path(root).resolve()
    top = git_output(root, 'rev-parse', '--show-toplevel')
    if not top:
        return (f'{root} をGitの作業コピーとして読めない。worktreeを作った環境か、'
                'GIT_DIR・GIT_WORK_TREE の指定を確認する')
    if Path(top).resolve() != root:
        return (f'git が別の作業ツリー {top} を指している。repo直下を渡したか、'
                'GIT_DIR・GIT_WORK_TREE の指定を確認する')
    # GIT_DIR alone can name another repository while the work tree still resolves here.
    # A `.git` link written in another environment cannot be resolved, but the worktree
    # name it ends with still has to be the one git reads.
    own = own_git_dir(root)
    actual = git_output(root, 'rev-parse', '--absolute-git-dir')
    if own and actual:
        actual = Path(actual).resolve()
        if own.exists():
            mismatch = actual != own
        else:
            mismatch = own.parent.name == 'worktrees' and (
                actual.parent.name != 'worktrees' or actual.name != own.name)
        if mismatch:
            return f'git が別のリポジトリ {actual} を読んでいる。GIT_DIR の指定を確認する'
    return None


def own_git_dir(root):
    """Resolve the repository that the working copy's own `.git` names."""
    marker = Path(root) / '.git'
    if marker.is_dir():
        return marker.resolve()
    if marker.is_file():
        text = marker.read_text(encoding='utf-8', errors='replace').strip()
        if text.startswith('gitdir:'):
            target = Path(text[len('gitdir:'):].strip())
            return (target if target.is_absolute() else Path(root) / target).resolve()
    return None


def default_base(root):
    """Name the remote default branch, `origin/HEAD` or else `origin/main`/`origin/master`.

    Changes are counted from there by default, since commits on the working branch would
    otherwise go unseen once the working tree is clean. None means none of them exists, and
    callers stop rather than look at the uncommitted changes alone.
    """
    for candidate in ('origin/HEAD', 'origin/main', 'origin/master'):
        if git_output(root, 'rev-parse', '--verify', '--quiet', f'{candidate}^{{commit}}'):
            return candidate
    return None


def default_branch(root):
    """Name the branch the default base points at, such as `main`, or None."""
    base = default_base(root)
    if base == 'origin/HEAD':
        target = git_output(root, 'symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD')
        return target.split('/', 1)[1] if '/' in target else None
    return base.split('/', 1)[1] if base else None



def repository_name(root):
    """Name the working copy by its origin remote, so worktrees report the repository."""
    url = git_output(root, 'remote', 'get-url', 'origin')
    if url:
        return re.sub(r'\.git$', '', url.rstrip('/').rsplit('/', 1)[-1])
    return Path(root).resolve().name


def branch_name(root):
    return git_output(root, 'branch', '--show-current') or git_output(
        root, 'rev-parse', '--short', 'HEAD') or '不明'
