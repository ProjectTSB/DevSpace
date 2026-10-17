"""Read-only Git queries about one working copy, shared by the checks under scripts/.

A working copy opened through GIT_DIR and GIT_WORK_TREE from another environment is
supported; `git_problem` tells when git would read some other tree or repository.
"""
import re
import subprocess
from pathlib import Path


class GitFailure(Exception):
    """A Git query that had to answer, such as the list of changes, failed."""


def git_output(root, *arguments, strip=True, required=False):
    """Query Git read-only; `strip=False` keeps the leading status characters.

    A failed query gives an empty string, or raises GitFailure when `required` is set:
    for a list of changes or files, an empty answer would read as "nothing to check".
    """
    # Without optional locks a query such as status does not refresh and rewrite the index,
    # which a parallel session may be writing.
    try:
        result = subprocess.run(('git', '--no-optional-locks', '-C', str(root)) + arguments,
                                capture_output=True, text=True, check=False)
    except OSError as error:
        if required:
            raise GitFailure(str(error)) from error
        return ''
    if result.returncode != 0:
        if required:
            raise GitFailure(result.stderr.strip().split('\n')[0])
        return ''
    return result.stdout.strip() if strip else result.stdout


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


def repository_name(root):
    """Name the working copy by its origin remote, so worktrees report the repository."""
    url = git_output(root, 'remote', 'get-url', 'origin')
    if url:
        return re.sub(r'\.git$', '', url.rstrip('/').rsplit('/', 1)[-1])
    return Path(root).resolve().name


def branch_name(root):
    return git_output(root, 'branch', '--show-current') or git_output(
        root, 'rev-parse', '--short', 'HEAD') or '不明'
