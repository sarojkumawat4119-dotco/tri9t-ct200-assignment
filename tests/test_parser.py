from pathlib import Path
from app.parser import parse_pdf
ROOT=Path(__file__).resolve().parents[1]
V1=ROOT/'data/ct200_manual.pdf'
V2=ROOT/'data/ct200_manual_v2.pdf'

def by_number(nodes, number): return [n for n in nodes if n['number']==number]

def test_duplicate_error_codes_headings_are_distinct_and_correctly_parented():
    nodes=parse_pdf(V1)
    matches=[n for n in nodes if n['heading']=='Error Codes']
    assert len(matches)==2
    assert [n['number'] for n in matches]==['4.2','7.1']
    assert nodes[matches[0]['parent_index']]['heading']=='Alarms and Safety Behavior'
    assert nodes[matches[1]['parent_index']]['heading']=='Troubleshooting'
    assert matches[0]['content_hash'] != matches[1]['content_hash'] or matches[0]['parent_index'] != matches[1]['parent_index']

def test_numbering_gap_is_preserved_without_fabricating_missing_heading():
    nodes=parse_pdf(V1)
    battery=by_number(nodes,'2.1.1.1')[0]
    assert battery['heading']=='Battery Life Under Typical Use'
    assert nodes[battery['parent_index']]['number']=='2.1'
    assert not any(n['number']=='2.1.1' for n in nodes)

def test_out_of_order_3_4_then_3_3_are_both_retained_under_section_3():
    nodes=parse_pdf(V1)
    auto=by_number(nodes,'3.4')[0]; result=by_number(nodes,'3.3')[0]
    assert auto['heading']=='Auto Shutoff'
    assert result['heading']=='Result Display and Classification'
    assert auto['parent_index']==result['parent_index']
    assert nodes[auto['parent_index']]['number']=='3'

def test_page_break_split_paragraph_is_reconstructed_and_content_not_dropped():
    nodes=parse_pdf(V1)
    profile=by_number(nodes,'3.1')[0]
    assert 'Press and hold the power button for one second' in profile['body_text']
    assert 'Use the profile button to select User 1 or User 2' in profile['body_text']

def test_v2_requirement_changes_are_detectable_and_new_section_is_retained():
    old=parse_pdf(V1); new=parse_pdf(V2)
    old_battery=by_number(old,'2.1.1.1')[0]; new_battery=by_number(new,'2.1.1.1')[0]
    assert '300 measurement cycles' in old_battery['body_text']
    assert '250 measurement cycles' in new_battery['body_text']
    assert old_battery['content_hash'] != new_battery['content_hash']
    assert by_number(new,'5.3')[0]['heading']=='Data Export'

def test_table_rows_remain_separate_lines():
    nodes=parse_pdf(V1); specs=by_number(nodes,'2.1')[0]
    assert 'Parameter Value\nMeasurement method Oscillometric\nPressure range 0–299 mmHg' in specs['body_text']
