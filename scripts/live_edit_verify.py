"""Opt-in paid HTTP E2E for the 5,000-line edit exercise.

Example: uv run python scripts/live_edit_verify.py --model openai/gpt-3.5-turbo --model openai/gpt-5.6-sol
Correctness is reported separately from API/tool-loop completion.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from common.core.config import load_config
from common.core.experiments import task_by_id
from scripts.web_client import web_runner


async def main(models):
    models = tuple(models or load_config().models)
    config = load_config().copy(model=models[0], models=models)
    output = Path('artifacts') / ('live-long-edit-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '.json')
    output.parent.mkdir(exist_ok=True)
    results = []
    async with web_runner(config) as runner:
        for model in models:
            await runner.new(model, 'code-edit')
            record = await runner.submit(task_by_id('code-edit').prompt)
            events = record['events']
            calls = [e['data']['name'] for e in events if e['kind'] == 'tool_start']
            responses = [e['data'] for e in events if e['kind'] == 'tool_end']
            errors = [e['data']['text'] for e in events if e['kind'] == 'error']
            result = {'model': model, 'run_id': record['id'], 'status': record['status'],
                'api_connected': any(e['kind'] == 'usage' for e in events),
                'tool_loop_completed': record['status'] == 'completed' and bool(responses)
                    and any(e['kind'] == 'assistant' for e in events),
                'edit_attempted': 'edit' in calls,
                'file_written': any(r['name'] == 'edit' and not r['result']['is_error']
                    and json.loads(r['result']['text']).get('saved') for r in responses),
                'tool_calls': calls, 'tool_errors': sum(r['result']['is_error'] for r in responses),
                'seconds': record['elapsed_seconds'], 'grade': record['grade'], 'errors': errors}
            results.append(result)
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False), flush=True)
    print(str(output), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', action='append')
    args = parser.parse_args()
    asyncio.run(main(args.model))
