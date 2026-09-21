from app.services.wanted_sync import parse_wanted_page

HTML = """
<html><body>
<table>
<tr><th>STT</th><th>Họ tên</th><th>Năm sinh</th><th>Nơi ĐKTT</th><th>Bố/mẹ</th><th>Tội danh</th><th>QĐ</th><th>Đơn vị</th></tr>
<tr>
<td>1</td>
<td><a href="/detail/abc">Nguyễn Văn A</a></td>
<td>1990</td>
<td>Tây Ninh</td>
<td>Nguyễn Văn B / Trần Thị C</td>
<td>Tội danh thử nghiệm</td>
<td>Số 123 ngày 01/01/2026</td>
<td>Cơ quan thử nghiệm</td>
</tr>
</table>
<a href="/page/2">2</a>
</body></html>
"""

def test_parse_wanted_table():
    rows, pages = parse_wanted_page(HTML, "https://truyna.bocongan.gov.vn/list")
    assert len(rows) == 1
    row = rows[0]
    assert row["full_name"] == "Nguyễn Văn A"
    assert row["birth_year"] == 1990
    assert row["registered_address"] == "Tây Ninh"
    assert row["detail_url"] == "https://truyna.bocongan.gov.vn/detail/abc"
    assert row["source_key"]
    assert "https://truyna.bocongan.gov.vn/page/2" in pages
