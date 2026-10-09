"""Read knowledge note headers and resolve per-working-copy path rules."""
import re
import subprocess
from pathlib import Path

KNOWLEDGE_DIR = 'docs/knowledge'
NOTES_DIR = 'docs/knowledge/notes'
ENTRY_DOC = 'docs/knowledge/README.md'

SCALAR_KEYS = ('title', 'description', 'area')
LIST_KEYS = ('paths', 'ids', 'related')
REQUIRED_KEYS = ('title', 'description')
TITLE_LIMIT = 60
DESCRIPTION_LIMIT = 120

# Cross-repository references name the repository instead of a parent-relative path,
# because each working copy places the dependency somewhere else.
KNOWN_REPOS = ('DevSpace', 'TheSkyBlessing', 'Asset', 'Asset-AnimatedJava', 'TSB-ResourcePack')

# Changing these files changes how every later session reads and updates knowledge,
# so a person merges them instead of the docs/tests automation.
DEVSPACE_PROTECTED = (
    'AGENTS.md',
    'CLAUDE.md',
    'docs/knowledge-maintenance.md',
    'docs/knowledge-notes.md',
    'scripts/knowledge/',
    'tests/knowledge.py',
)
CHILD_PROTECTED = (
    'AGENTS.md',
    'docs/knowledge/README.md',
    '.github/workflows/auto-merge-docs-tests.yml',
    '.github/tests/auto-merge-docs-tests.test.cjs',
)

NOTE_NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*\.md$')
AREA_SEGMENT = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
MARKDOWN_LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
CROSS_REPO_REF = re.compile(r'^(%s):(.+)$' % '|'.join(KNOWN_REPOS))


class Document:
    """One indexed document: its path, header fields and the body that follows."""

    def __init__(self, root, relative):
        self.root = Path(root)
        self.relative = relative.replace('\\', '/')
        self.text = (self.root / self.relative).read_text(encoding='utf-8').replace('\r\n', '\n')
        self.header, self.header_errors, self.body = parse_header(self.text)
        self.has_header = not self.header_errors or bool(self.header)

    @property
    def is_note(self):
        return self.relative.startswith(NOTES_DIR + '/')

    @property
    def kind(self):
        return 'ノート' if self.is_note else '領域文書'

    @property
    def area(self):
        if self.header.get('area'):
            return self.header['area']
        if self.is_note:
            segments = self.relative[len(NOTES_DIR) + 1:].split('/')[:-1]
            return '/'.join(segments) if segments else 'その他'
        return '領域文書'

    @property
    def title(self):
        return self.header.get('title') or heading_title(self.body) or self.relative

    @property
    def description(self):
        return self.header.get('description', '')


def parse_header(text):
    """Split a leading `---` block into fields, reporting the shape problems found."""
    errors = []
    if not text.startswith('---\n'):
        return {}, ['ヘッダーがない: 先頭行から `---` で囲んだ title・description を置く'], text
    end = text.find('\n---\n', 3)
    if end < 0:
        return {}, ['ヘッダーの終端 `---` がない'], text
    header, body = text[4:end + 1], text[end + 5:]
    fields, key = {}, None
    for number, line in enumerate(header.split('\n'), start=2):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        item = re.match(r'^\s*-\s+(.*)$', line)
        if item:
            if key is None or not isinstance(fields.get(key), list):
                errors.append(f'{number}行目: 対応するリストのキーがない: {line.strip()}')
            else:
                fields[key].append(unquote(item.group(1)))
            continue
        pair = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$', line)
        if not pair:
            errors.append(f'{number}行目: `キー: 値` か `  - 要素` だけを書く: {line.strip()}')
            continue
        key, value = pair.group(1), pair.group(2).strip()
        if key in fields:
            errors.append(f'{number}行目: キーが重複している: {key}')
            continue
        if key in SCALAR_KEYS:
            fields[key] = unquote(value)
        elif key in LIST_KEYS:
            fields[key] = flow_list(value) if value else []
        else:
            allowed = ', '.join(SCALAR_KEYS + LIST_KEYS)
            errors.append(f'{number}行目: 使えないキー: {key}（使えるのは {allowed}）')
    for key in SCALAR_KEYS:
        if isinstance(fields.get(key), list):
            errors.append(f'{key} は1行の値で書く')
    return fields, errors, body


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        return value[1:-1]
    return value


def flow_list(value):
    if value.startswith('[') and value.endswith(']'):
        return [unquote(item) for item in value[1:-1].split(',') if item.strip()]
    return [unquote(value)]


def heading_title(body):
    for line in body.split('\n'):
        if line.startswith('# '):
            return line[2:].strip()
        if line.strip():
            return ''
    return ''


def validate(document):
    """Report header, naming and reference problems of one document."""
    messages = list(document.header_errors)
    if document.has_header:
        messages.extend(header_findings(document))
    messages.extend(body_findings(document))
    return messages


def header_findings(document):
    """Check the fields that the INDEX reads, and their correspondence with the body."""
    header = document.header
    for key in REQUIRED_KEYS:
        if not header.get(key):
            yield f'{key} が空である'
    if len(header.get('title', '')) > TITLE_LIMIT:
        yield f'title が長い: {len(header["title"])}文字（上限 {TITLE_LIMIT}）'
    if len(header.get('description', '')) > DESCRIPTION_LIMIT:
        yield (f'description が長い: {len(header["description"])}文字（上限 {DESCRIPTION_LIMIT}）'
               '。どの作業で読むかを一文で書き、詳細は本文へ置く')
    if header.get('area') and not AREA_SEGMENT.match(header['area'].split('/')[0]):
        yield 'area は英小文字・数字・ハイフンで書く'
    heading = heading_title(document.body)
    if header.get('title') and heading != header['title']:
        yield f'本文の見出しがヘッダーと違う: `# {heading}` と title `{header["title"]}`'
    yield from check_paths(document)
    yield from check_references(document)


def body_findings(document):
    """Check the placement, naming and links that hold regardless of the header."""
    if document.is_note:
        name = document.relative.rsplit('/', 1)[-1]
        if not NOTE_NAME.match(name):
            yield f'ノートのファイル名は英小文字・数字・ハイフンにする: {name}'
    elif '/' in document.relative[len(KNOWLEDGE_DIR) + 1:]:
        yield f'{KNOWLEDGE_DIR}/ 直下か {NOTES_DIR}/ 配下に置く'
    if not [line for line in document.body.split('\n')
            if line.strip() and not line.startswith('# ')]:
        yield '本文が見出しだけである: 根拠と適用条件を残す'
    yield from check_links(document)


def check_paths(document):
    for value in document.header.get('paths', []):
        if value.startswith('/') or '..' in value.split('/'):
            yield f'paths はrepo直下からの相対パスで書く: {value}'
        elif not (document.root / value).exists():
            yield f'paths の対象が作業コピーにない: {value}'


def check_references(document):
    """Resolve `related` from the repository root of the same working copy."""
    for value in document.header.get('related', []):
        if value.startswith(('http://', 'https://')):
            continue
        cross = CROSS_REPO_REF.match(value)
        if cross:
            if cross.group(2).startswith('/'):
                yield f'related の依存repo参照はrepo直下からの相対パスで書く: {value}'
            continue
        target = value.split('#', 1)[0]
        if not target:
            yield f'related に参照先のファイルがない: {value}'
        elif target.startswith('/') or '..' in target.split('/'):
            yield f'related はrepo直下からの相対パス、URL、`<repo名>:<パス>` で書く: {value}'
        elif not (document.root / target).exists():
            yield f'related の参照先が作業コピーにない: {value}'


def check_links(document):
    """Resolve body links from the document, like a reader following them."""
    directory = (document.root / document.relative).parent
    for link in MARKDOWN_LINK.findall(document.body):
        if link.startswith(('http://', 'https://', 'mailto:', '#')):
            continue
        if link.startswith('/'):
            yield f'本文のリンクに絶対パスを使っている: {link}'
            continue
        if not (directory / link.split('#', 1)[0]).exists():
            yield f'本文のリンク先が作業コピーにない: {link}'


def documents(root, area=None, notes_only=False):
    """Collect the knowledge documents of one working copy in a stable order."""
    base = Path(root) / KNOWLEDGE_DIR
    found = []
    for path in sorted(base.rglob('*.md')):
        relative = path.relative_to(root).as_posix()
        if relative == ENTRY_DOC:
            continue
        document = Document(root, relative)
        if notes_only and not document.is_note:
            continue
        if area and document.area != area:
            continue
        found.append(document)
    return found


def is_devspace(root):
    return (Path(root) / 'docs/knowledge-maintenance.md').exists()


def protected_paths(root):
    return DEVSPACE_PROTECTED if is_devspace(root) else CHILD_PROTECTED


def protected_hits(root, relatives):
    rules = protected_paths(root)
    return [path for path in relatives
            if any(path == rule or (rule.endswith('/') and path.startswith(rule))
                   for rule in rules)]


def git_output(root, *arguments, strip=True):
    """Query Git read-only; `strip=False` keeps the leading status characters."""
    try:
        result = subprocess.run(('git', '-C', str(root)) + arguments,
                                capture_output=True, text=True, check=False)
    except OSError:
        return ''
    if result.returncode != 0:
        return ''
    return result.stdout.strip() if strip else result.stdout


def repository_name(root):
    """Name the working copy by its origin remote, so worktrees report the repository."""
    url = git_output(root, 'remote', 'get-url', 'origin')
    if url:
        return re.sub(r'\.git$', '', url.rstrip('/').rsplit('/', 1)[-1])
    return Path(root).resolve().name


def branch_name(root):
    return git_output(root, 'branch', '--show-current') or git_output(
        root, 'rev-parse', '--short', 'HEAD') or '不明'
