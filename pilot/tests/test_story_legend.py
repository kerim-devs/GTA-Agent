import pytest

from pilot.legend import Entry, LegendWaypoint, kind_of, read_legend


@pytest.mark.parametrize(
    "name",
    ["Immobilie: McKenzie-Feldhangar: 150.000 $", "Property for sale", "Hangar 200000 €", "Purchase hangar"],
)
@pytest.mark.parametrize("args", [{"kind": "mission"}, {"kind": "other"}, {"kind": "shop"}])
def test_purchase_entries_are_never_wanted(name, args):
    assert kind_of(name) == "property"
    entry = Entry(name, "other")
    assert not LegendWaypoint(args)._wanted(entry)
    assert not LegendWaypoint({"place": name})._wanted(entry)


def test_recorded_property_row_remains_navigable_but_cannot_be_confirmed():
    name = "Immobilie: McKenzie-Feldhangar: 150.000 $"
    legend = read_legend(
        [
            {"text": name + " < 1/4 >", "box": (884, 70, 306, 14)},
            {"text": "Markierung wählen Wegpunkt", "box": (780, 658, 410, 28)},
        ]
    )
    assert legend.selected.name == name
    assert legend.selected.kind == "property"
    assert not LegendWaypoint({"place": name})._wanted(legend.selected)
