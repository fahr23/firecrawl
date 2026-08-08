from unittest.mock import Mock, patch

import pytest

from scrapers.isyatirim_fundamentals import fetch_fundamentals


HTML = """
<div class="box"><div class="box-title"><h3>Mali Tablo**</h3></div>
<select id="ddlMaliTabloFirst"><option selected>2026/3</option></select>
<select id="ddlMaliTabloSecond"><option selected>2025/12</option></select>
<select id="ddlMaliTabloDonem1"><option selected>2026/3</option></select>
<select id="ddlMaliTabloDonem2"><option selected>2025/12</option></select>
<select id="ddlMaliTabloDonem3"><option selected>2025/9</option></select>
<select id="ddlMaliTabloDonem4"><option selected>2025/6</option></select>
<tbody id="malitabloShortTbody">
  <tr><td>Özkaynaklar</td><td>966.388,0</td></tr>
  <tr><td>Ödenmiş Sermaye</td><td>1.380,0</td></tr>
  <tr><td>Net Kâr</td><td>9.915,0</td></tr>
</tbody></div>
<div class="box"><div class="box-title"><h3>Cari Değerler*</h3></div><table>
  <tr><th>F/K</th><td>3,1</td></tr><tr><th>FD/FAVÖK</th><td>5,2</td></tr>
  <tr><th>PD/DD</th><td>0,5</td></tr><tr><th>FD/Satışlar</th><td>0,9</td></tr>
  <tr><th>Yabancı Oranı (%)</th><td>26,01</td></tr><tr><th>Piyasa Değeri</th><td>433.320,0 mnTL</td></tr>
  <tr><th>Net Borç</th><td>530.401,0 mnTL</td></tr><tr><th>Halka Açıklık Oranı (%)</th><td>50,2</td></tr>
</table></div>
<table data-csvname="malitablo"><tbody>
  <tr><td>TOPLAM VARLIKLAR</td><td>2.158.033.000.000</td><td>2.197.221.560.937</td><td>1.794.446.000.000</td><td>1.652.589.000.000</td></tr>
  <tr><td>Dönem Net Kar/Zararı</td><td>9.915.000.000</td><td>130.076.282.287</td><td>81.064.000.000</td><td>25.013.000.000</td></tr>
</tbody></table>
"""


def test_fetch_fundamentals_normalizes_company_card_values_and_preserves_million_try_unit():
    response = Mock(text=HTML)
    with patch("scrapers.isyatirim_fundamentals.requests.get", return_value=response) as get:
        result = fetch_fundamentals("thyao")

    assert get.call_args.kwargs["params"] == {"hisse": "THYAO"}
    assert result["statement_unit"] == "million TRY"
    assert result["reported_periods"] == ["2026/3", "2025/12"]
    assert result["statement_snapshot"] == {
        "equity_million_try": 966388.0,
        "paid_in_capital_million_try": 1380.0,
        "net_income_million_try": 9915.0,
    }
    assert result["current_valuation"]["price_to_earnings"] == 3.1
    assert result["current_valuation"]["net_debt_million_try"] == 530401.0
    assert result["one_year_statement_history"][0]["report_period"] == "2026/3"
    assert result["one_year_statement_history"][0]["items"][0] == {
        "label": "TOPLAM VARLIKLAR", "value_try": 2158033000000.0,
    }


def test_fetch_fundamentals_rejects_invalid_ticker_without_requesting_source():
    with patch("scrapers.isyatirim_fundamentals.requests.get") as get:
        with pytest.raises(ValueError, match="invalid BIST instrument"):
            fetch_fundamentals("THYAO?x=1")
    get.assert_not_called()
