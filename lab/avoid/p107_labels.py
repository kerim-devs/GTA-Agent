"""Visual labels for all 170 recorded onsets; IDs are printed on the contact sheets.

These describe the scene, not a detector identity or proof of a collision path.
Crossing includes pedestrians on the driven path. Nothing includes a distant
vehicle with no visible conflict, and the player's own car after a collision.
"""

import json

from p107_measure import HERE

LABELS = {
    '051709': 'C C C N S S O N Q B C S C C S Q Q Q Q Q Q B Q S O O B B Q Q',
    '052018': 'C C S Q Q Q B N S S S C S N O',
    '052402': 'S C O O O O N S Q Q C C B N C S Q O O O',
    '052653': 'C C C C N N Q N C C Q N C N N N Q Q',
    '053655': 'C C C O O O C S S N S S O S S C C C C C S S S C C N',
    '054734': 'O O O N S Q Q Q S C B B N N N N C C C S Q Q S',
    '055349': 'C Q N C C S S S O Q Q Q C Q Q O S S C',
    '055729': 'N N N N N C S B N O O S S S C O N S N',
}
CLASSES = {'Q': 'standing', 'S': 'slower', 'O': 'oncoming', 'C': 'crossing',
           'B': 'beside', 'N': 'nothing'}
NOTES = {
    '051709': {
        1: 'Side collision with traffic at the junction; the own car begins to roll.',
        2: 'Same side collision, already pitched up.', 3: 'Already on top of the other car; not clean following.',
        4: 'Own car rolling, no lead vehicle visible.',
        8: 'Very distant lead traffic; no near conflict visible.',
        10: 'Queue is left of the sidewalk trajectory.',
        11: 'Van crosses far to the left; own part of the junction is empty.',
        12: 'SUV ahead draws away left while own car turns right; competing oncoming traffic.',
        13: 'Pedestrian in sidewalk trajectory.', 14: 'Same pedestrian and pavement turn.',
        21: 'Queue squeezed between lanes; side contact also visible.',
        26: 'Oncoming sports car at the left of the right bend, outside own lane.',
        27: 'People on pavement beside the right bend, roadway clear.',
        28: 'Same people beside the right bend.',
    },
    '052018': {1: 'Cross traffic while pulling out from pavement.', 2: 'Same cross traffic.',
              7: 'People on the pavement beside the turn.',
              8: 'Only distant traffic ahead.', 14: 'Own car spinning; no object ahead.',
              15: 'Oncoming vehicle near the centre line; path separation uncertain.'},
    '052402': {3: 'Oncoming lights under the bridge left of own lane.',
              7: 'Own lane clear; only far traffic.',
              11: 'Bus crossing far ahead at the junction.',
              12: 'Crossing brown car and approaching white car during a right turn.',
              13: 'Own car tipped at pavement; passing vehicle on road beside it.',
              14: 'Palm/tree impact; no detected-road-user reason visible.',
              15: 'Pedestrian directly in sidewalk trajectory.',
              18: 'Own car turns toward opposite traffic; separation uncertain.',
              19: 'Opposite traffic after the turn; separation uncertain.',
              20: 'Same opposite traffic; own lane position uncertain.'},
    '052653': {4: 'Pedestrians directly in sidewalk trajectory.', 5: 'Own car at a tree.',
              6: 'Clear downhill lane and pavement.', 7: 'Parked van in own curb trajectory.',
              8: 'Own car pitching after pavement impact.',
              11: 'Truck ahead at right turn; car then hits kerb.',
              12: 'Clear junction.', 13: 'Side impact at junction.',
              14: 'Own car rolling after impact.', 15: 'Own car spinning.', 16: 'Same spin.'},
    '053655': {6: 'Head-on contact under bridge; own car has crossed into opposing path.',
              10: 'Clear road after pavement impact.',
              16: 'Cross traffic at turn with side contact.', 17: 'Pedestrian on pavement trajectory.',
              18: 'Bus crosses directly through path.', 19: 'Same bus after contact.',
              20: 'Same bus after contact.', 24: 'Pedestrian in sidewalk trajectory.',
              25: 'Same pedestrian and pole impact.', 26: 'Person now down beside own car; no lead hazard.'},
    '054734': {1: 'Opposing cars during right turn.', 2: 'Same opposing cars.',
              3: 'Same opposing cars, now outside turning path.',
              4: 'Road clear; distant traffic only.', 10: 'Pedestrian hit in road trajectory.',
              12: 'Own car spinning beside bus.', 13: 'Own car spinning; road clear.',
              14: 'Same spin.', 15: 'Own car rolling after pavement impact.',
              16: 'Same roll.', 19: 'Repeated brake after cross-traffic side impact.',
              21: 'Parked vehicle directly in pavement trajectory.', 22: 'Truck in path at junction.'},
    '055349': {2: 'Van in curb trajectory.', 3: 'Tree/pavement impact, no lead object.',
              4: 'Distant cross traffic, no immediate conflict visible.',
              5: 'Same distant crossing vehicle.', 9: 'Approaching motorcycle at junction.',
              13: 'Police car crosses and strikes from the left.',
              16: 'Oncoming black car passes left of SUV.'},
    '055729': {1: 'Own car mounting empty median.', 2: 'Same median, no road user ahead.',
              3: 'Same median, sign struck.', 4: 'Own car airborne at palm tree.',
              5: 'Same tree impact.', 8: 'Cars alongside on right, own lane open.',
              9: 'Clear split junction.', 10: 'Oncoming lorry left of lane.',
              11: 'Same oncoming lorry.', 17: 'Own lane open; traffic distant.',
              19: 'Empty sidewalk trajectory; distant traffic.'},
}


if __name__ == '__main__':
    recorded = json.loads((HERE / 'p107-recorded.json').read_text())
    labelled = {}
    totals = {c: {'count': 0, 'seconds': 0, 'gps_loss_sum': 0, 'gps_known': 0} for c in CLASSES.values()}
    for session, codes in LABELS.items():
        events = recorded[session]['events']
        assert len(codes.split()) == len(events), session
        labelled[session] = []
        for event, code in zip(events, codes.split(), strict=True):
            row = {**event, 'class': CLASSES[code], 'note': NOTES.get(session, {}).get(event['id'], ''),
                   'sheet': f"p107-{session}-sheet-{(event['id']-1)//5+1}.jpg"}
            labelled[session].append(row)
            total = totals[row['class']]
            total['count'] += 1
            total['seconds'] += event['seconds']
            if event['lost'] is not None:
                total['gps_loss_sum'] += event['lost']
                total['gps_known'] += 1
    (HERE / 'p107-labels.json').write_text(json.dumps(labelled, indent=2) + '\n')
    print(json.dumps(totals, indent=2))
