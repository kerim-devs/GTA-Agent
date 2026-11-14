"""Attach the manual frame review to every after-onset; uncertain cases count against acceptance."""

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parents[1] / 'docs/reports/P106-the-car-brakes-for-what-stands-in-its-lane.md'
MARKER = '\nEvery after-onset is listed below'
NAMES = {
    'same-clean': '035459', 'day-clean': '040426', 'rain-start': '024817',
    'rain-clean': '024817', 'rain-end': '024817', 'freeway-clean': '005357',
}
FAULTS = {
    'day-clean': {
        115.072: 'Oncoming vehicle left of the own lane',
        129.454: 'Duplicate box on the own white car after the impact',
        129.637: 'Duplicate own-car box, a second onset in the same incident',
        145.851: 'Lorry left beside the right-hand bend after the intended path turns away',
    },
    'rain-clean': {47.166: 'White car in the adjacent right lane'},
    'rain-end': {
        92.578: 'Oversized false vehicle box over the road/own car',
        97.299: 'Oversized false vehicle box over the road/own car',
    },
}
UNCERTAIN = {
    'same-clean': {
        260.893: 'Small vehicle box after the intersection turn; collision path unproved',
        263.477: 'Small car-labelled box at the palm tree; identity and brake attribution unproved',
    },
    'day-clean': {
        137.461: 'Small vehicle beyond the adjacent lorry; target association unproved',
        166.841: 'Vehicle beyond the junction while the own car turns onto the pavement',
    },
    'rain-clean': {
        60.465: 'Central traffic at the junction; lane ownership unproved',
        60.931: 'Same junction traffic, repeated onset; lane ownership unproved',
        61.265: 'Same junction traffic, repeated onset; lane ownership unproved',
        61.498: 'Same junction traffic, repeated onset; lane ownership unproved',
        67.252: 'Vehicle right beside the current track; the retained threat may already be clear',
    },
}


if __name__ == '__main__':
    summary = json.loads((HERE / 'p106-replay-summary.json').read_text())
    text = MARKER + ', including repeats of an old request, so no newly introduced pulse is omitted. '
    text += 'Times are command-tick times; frame IDs identify the earlier detector frame shown in the linked sheets. '
    text += '“Old active” means the old avoider requests L2 on that same tick, not that onset times match. '
    text += '“Observed traffic” names a visible reason; it does not prove that full L2 was necessary or that a counterfactual pass would succeed. '
    text += '“Unproved” is counted as a fault in the conservative acceptance total.\n'
    review = []
    for name, session in NAMES.items():
        events = summary[name]['events']['after']
        sheets = [f'[frames {i+1}](../../lab/avoid/p106-{name}-brakes-{i+1}.jpg)'
                  for i in range((len(events)+11)//12)]
        text += f'\nRecording `{session}`, batch `{name}`: ' + ', '.join(sheets) + '.\n\n'
        text += '| Onset s | Detector frame | Old active | Visual assessment |\n| --- | --- | --- | --- |\n'
        for event in events:
            stamp = round(event['t'], 3)
            verdict = 'observed traffic'
            reason = 'Closing car ahead or crossing the junction'
            if name == 'same-clean':
                reason = 'Black car crossing the intersection'
            elif name == 'rain-start':
                reason = 'Queue ahead' if stamp < 20 else 'Car crossing the intersection'
            elif name == 'freeway-clean':
                reason = 'Closing vehicle ahead on the freeway'
            if event['threats'] and event['threats'][0]['kind'] in ('truck', 'bus'):
                reason = 'Closing lorry ahead'
            if stamp in FAULTS.get(name, {}):
                verdict, reason = 'fault', FAULTS[name][stamp]
            elif stamp in UNCERTAIN.get(name, {}):
                verdict, reason = 'unproved', UNCERTAIN[name][stamp]
            text += f'| {stamp:.3f} | {event["frame_id"]} | {"yes" if event["other_brakes"] else "no"} | {verdict}: {reason} |\n'
            review.append({'session': session, 'batch': name, 'onset': stamp, 'frame_id': event['frame_id'],
                           'old_active': event['other_brakes'], 'verdict': verdict, 'reason': reason})
    (HERE / 'p106-brake-review.json').write_text(json.dumps(review, indent=2) + '\n')
    REPORT.write_text(REPORT.read_text().split(MARKER)[0] + text)
    counts = Counter(r['verdict'] for r in review)
    added = sum(r['verdict'] != 'observed traffic' and not r['old_active'] for r in review)
    print(dict(counts), 'fault/unproved without old brake', added, 'total', len(review))
