import pathlib
import uuid
import datetime
import json
import re
from ledger import EventKind, read_session, with_file_lock

SENSITIVE_KEYWORDS = {
    'medical': ['diagnosis', 'prescription', 'symptom', 'doctor', 'hospital', 'medication'],
    'financial': ['account number', 'routing number', 'ssn', 'social security', 'bank account', 'credit card'],
    'legal': ['lawsuit', 'subpoena', 'attorney', 'settlement'],
    'identity': ['passport number', 'driver license number', 'date of birth']
}

def contains_keyword(val, keywords) -> bool:
    if isinstance(val, str):
        val_lower = val.lower()
        return any(kw in val_lower for kw in keywords)
    elif isinstance(val, dict):
        return any(contains_keyword(v, keywords) for v in val.values())
    elif isinstance(val, list):
        return any(contains_keyword(v, keywords) for v in val)
    return False

def should_journal(event: dict, session_events: list[dict]) -> bool:
    try:
        kind = event.get('kind')
        payload = event.get('payload')
        if payload is None or not isinstance(payload, dict):
            payload = {}

        if kind == 'decision_confirmed':
            return True
        elif kind == 'decision_proposed':
            return False
        elif kind == 'op_end':
            state = payload.get('state')
            if state == 'completed':
                return payload.get('verified') is True
            elif state == 'failed':
                op_id = event.get('operation_id')
                if not op_id:
                    return False
                fail_count = 0
                for e in session_events:
                    e_payload = e.get('payload')
                    if e_payload is None or not isinstance(e_payload, dict):
                        e_payload = {}
                    if (e.get('kind') == 'op_end' and
                        e_payload.get('state') == 'failed' and
                        e.get('operation_id') == op_id):
                        fail_count += 1
                    if e.get('event_id') == event.get('event_id'):
                        break
                return fail_count == 2
            return False
        elif kind == 'route_decided':
            return payload.get('resolved') is True
        return False
    except Exception:
        return False

def dedupe_key(event: dict) -> tuple:
    payload = event.get('payload')
    if payload is None or not isinstance(payload, dict):
        payload = {}
    return (
        event.get('project'),
        payload.get('action'),
        payload.get('affected_object'),
        payload.get('outcome')
    )

def compose_entry(events: list[dict], correction_of: str | None = None, relation: str | None = None) -> str:
    if not events:
        raise ValueError("events list cannot be empty")

    if relation is not None and relation not in ('incorrect', 'reversed', 'state-changed-since'):
        raise ValueError("Invalid relation")
    if correction_of is not None and relation is None:
        raise ValueError("relation is required if correction_of is given")

    first_event = events[0]
    ts = first_event.get('ts', '')
    hh_mm = ts.split('T')[1][:5] if 'T' in ts else "00:00"

    first_payload = first_event.get('payload')
    if first_payload is None or not isinstance(first_payload, dict):
        first_payload = {}
    title = f"{first_payload.get('action', 'Update')}"

    bullets = []
    for event in events:
        project = event.get('project')
        kind = event.get('kind')
        payload = event.get('payload')
        if payload is None or not isinstance(payload, dict):
            payload = {}

        matched_topic = None
        for topic, keywords in SENSITIVE_KEYWORDS.items():
            if contains_keyword(payload, keywords):
                matched_topic = topic
                break

        if matched_topic:
            bullet = f"Worked on a {matched_topic} matter for {project}."
        else:
            bullet = f"{project}: {payload.get('action', kind)}"
        bullets.append(f"- {bullet}")

    new_id = str(uuid.uuid4())
    project = first_event.get('project')
    kind = first_event.get('kind')

    op_ids = sorted(set(e.get('operation_id') for e in events if e.get('operation_id')))
    ops_str = ",".join(op_ids)

    footer = f"<!-- id: {new_id} | project: {project} | kind: {kind} | ops: {ops_str}"
    if correction_of is not None:
        footer += f" | supersedes: {correction_of} | relation: {relation}"
    footer += " -->\n"

    bullets_str = "\n".join(bullets)
    return f"### {hh_mm} — {title}\n{bullets_str}\n\n{footer}"

def append_journal_entry(entry_md: str, index_row: dict, journal_dir: pathlib.Path) -> None:
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = journal_dir / 'JOURNAL.md'
    index_path = journal_dir / 'index.jsonl'

    with with_file_lock(journal_path):
        today = datetime.date.today().isoformat()
        header_line = f"## {today}"

        if journal_path.exists():
            content = journal_path.read_text(encoding='utf-8')
        else:
            content = ""

        lines = content.splitlines()
        first_header_idx = -1
        for i, line in enumerate(lines):
            if line.strip():
                if line.strip() == header_line:
                    first_header_idx = i
                break

        if first_header_idx != -1:
            new_lines = lines[:first_header_idx + 1] + [entry_md.rstrip('\n')] + lines[first_header_idx + 1:]
            new_content = "\n".join(new_lines) + "\n"
        else:
            new_content = f"{header_line}\n{entry_md}"
            if content:
                new_content += "\n" + content

        journal_path.write_text(new_content, encoding='utf-8')

    with open(index_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(index_row) + '\n')

def run_safety_net(session_id: str, journal_dir: pathlib.Path, ledger_base_dir: pathlib.Path) -> int:
    session_events = read_session(session_id, base_dir=ledger_base_dir)

    committed_ids = set()
    for event in session_events:
        if event.get('kind') == 'journal_committed':
            payload = event.get('payload') or {}
            if isinstance(payload, dict) and payload.get('event_id'):
                committed_ids.add(payload.get('event_id'))

    written_count = 0
    for idx, event in enumerate(session_events):
        event_id = event.get('event_id')
        if not event_id or event_id in committed_ids:
            continue

        if should_journal(event, session_events):
            entry_md = compose_entry([event])

            uuid_match = re.search(r"<!-- id: ([a-f0-9\-]+)", entry_md)
            entry_id = uuid_match.group(1) if uuid_match else ""

            index_row = {
                'id': entry_id,
                'ts': event.get('ts'),
                'project': event.get('project'),
                'kind': event.get('kind')
            }
            append_journal_entry(entry_md, index_row, journal_dir)
            written_count += 1

    return written_count
