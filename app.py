from flask import Flask, render_template, request, send_file
import numpy as np
import numpy_financial as npf
import plotly.graph_objs as go
import plotly.io as pio
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import json

app = Flask(__name__)

def years_months(period_float):
    if period_float is None:
        return "Not reached"
    years = int(period_float)
    months = int(round((period_float - years) * 12))
    if months == 12:
        years += 1
        months = 0
    parts = []
    if years > 0:
        parts.append(f"{years} year{'s' if years > 1 else ''}")
    if months > 0:
        parts.append(f"{months} month{'s' if months > 1 else ''}")
    return " ".join(parts) if parts else "0 months"

def payback_period(cash_flows, investment):
    cumulative = 0
    for i, cf in enumerate(cash_flows):
        cumulative += cf
        if cumulative >= investment:
            prev_cum = cumulative - cf
            remainder = investment - prev_cum
            fraction = remainder / cf if cf != 0 else 0
            return i + fraction
    return None

def discounted_payback_period(cash_flows, investment, discount_rate):
    cumulative = 0
    for i, cf in enumerate(cash_flows):
        discounted_cf = cf / ((1 + discount_rate) ** (i + 1))
        cumulative += discounted_cf
        if cumulative >= investment:
            prev_cum = cumulative - discounted_cf
            remainder = investment - prev_cum
            fraction = remainder / discounted_cf if discounted_cf != 0 else 0
            return i + fraction
    return None

def arr(cash_flows, investment, salvage_value):
    n = len(cash_flows)
    depreciation = (investment - salvage_value) / n if n > 0 else 0
    # Approximate accounting profit = cash flow - depreciation
    profits = [cf - depreciation for cf in cash_flows]
    average_profit = np.mean(profits) if profits else 0
    average_inv = (investment + salvage_value) / 2
    return (average_profit / average_inv) * 100 if average_inv != 0 else 0

def irr(cash_flows_incl_investment):
    try:
        return npf.irr(cash_flows_incl_investment)
    except:
        return None

def npv(discount_rate, cash_flows_incl_investment):
    return npf.npv(discount_rate, cash_flows_incl_investment)

def mirr(cash_flows_incl_investment, finance_rate, reinvest_rate):
    try:
        return npf.mirr(cash_flows_incl_investment, finance_rate, reinvest_rate)
    except:
        return None

def profitability_index(cash_flows, investment, discount_rate):
    discounted_sum = sum([cf / ((1 + discount_rate) ** (i + 1)) for i, cf in enumerate(cash_flows)])
    return discounted_sum / investment

@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    comparison_chart_div = None
    investments = []
    if request.method == 'POST':
        i = 0
        while True:
            key_inv = f'investment_{i}'
            key_disc = f'discount_rate_{i}'
            key_cf = f'cash_flows_{i}'
            key_salvage = f'salvage_value_{i}'
            if key_inv not in request.form:
                break
            try:
                investment_amt = float(request.form[key_inv])
                salvage_value = float(request.form.get(key_salvage, '0') or 0)
                discount_rate = float(request.form[key_disc]) / 100
                cash_flows_str = request.form[key_cf]
                cash_flows = [float(x.strip()) for x in cash_flows_str.split(',')]
                investments.append({
                    'name': f'Investment {i+1}',
                    'investment': investment_amt,
                    'salvage_value': salvage_value,
                    'discount_rate': discount_rate,
                    'cash_flows': cash_flows
                })
            except:
                pass
            i += 1

        irrs = []
        npvs = []
        pis = []
        names = []
        for inv in investments:
            inv_amt = inv['investment']
            salvage_val = inv['salvage_value']
            disc_rate = inv['discount_rate']
            cf = inv['cash_flows']
            cf_with_inv = [-inv_amt] + cf

            pbp = payback_period(cf, inv_amt)
            dpbp = discounted_payback_period(cf, inv_amt, disc_rate)
            arr_val = arr(cf, inv_amt, salvage_val)
            irr_val = irr(cf_with_inv)
            npv_val = npv(disc_rate, cf_with_inv)
            mirr_val = mirr(cf_with_inv, disc_rate, disc_rate)
            pi_val = profitability_index(cf, inv_amt, disc_rate)

            result = {
                'name': inv['name'],
                'Investment Amount': f"₹{inv_amt:,.2f}",
                'Salvage Value': f"₹{salvage_val:,.2f}",
                'Cash Flows': ", ".join([f"₹{cf:,.2f}" for cf in cf]),
                'Payback Period': years_months(pbp),
                'Discounted Payback Period': years_months(dpbp),
                'Accounting Rate of Return (ARR)': f"{arr_val:.2f} %",
                'Internal Rate of Return (IRR)': f"{irr_val*100:.2f} %" if irr_val else "Calculation error",
                'Net Present Value (NPV)': f"{npv_val:.2f}",
                'Modified IRR (MIRR)': f"{mirr_val*100:.2f} %" if mirr_val else "Calculation error",
                'Profitability Index': f"{pi_val:.2f}"
            }
            results.append(result)

            names.append(inv['name'])
            irrs.append(irr_val*100 if irr_val else 0)
            npvs.append(npv_val)
            pis.append(pi_val)

        fig = go.Figure(data=[
            go.Bar(name='IRR (%)', x=names, y=irrs, marker_color='rgb(26, 118, 255)'),
            go.Bar(name='NPV', x=names, y=npvs, marker_color='rgb(55, 83, 109)'),
            go.Bar(name='Profitability Index', x=names, y=pis, marker_color='rgb(50, 205, 50)')
        ])
        fig.update_layout(
            barmode='group',
            title='Investment Comparison',
            xaxis_title='Investment Options',
            yaxis_title='Value',
            template='plotly_dark',
            hovermode='x unified'
        )
        comparison_chart_div = pio.to_html(fig, full_html=False)

    return render_template('index.html', results=results, comparison_chart_div=comparison_chart_div, investments=investments)

@app.route('/download_report', methods=['POST'])
def download_report():
    investments_json = request.form['investments']
    results_json = request.form['results']

    investments = json.loads(investments_json)
    results = json.loads(results_json)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Investment Decision Support System Report")

    y = height - 90
    c.setFont("Helvetica", 12)

    for inv, res in zip(investments, results):
        if y < 100:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, y, "Investment Decision Support System Report Continued")
            y -= 40
            c.setFont("Helvetica", 12)

        c.drawString(50, y, f"{inv['name']}:")
        y -= 20
        c.drawString(60, y, f"Investment Amount: ₹{inv['investment']}")
        y -= 20
        c.drawString(60, y, f"Salvage Value: ₹{inv['salvage_value']}")
        y -= 20
        c.drawString(60, y, f"Discount Rate: {inv['discount_rate']*100:.2f} %")
        y -= 20
        c.drawString(60, y, f"Cash Flows: {', '.join(str(cf) for cf in inv['cash_flows'])}")
        y -= 25

        for key, value in res.items():
            if key == "name":
                continue
            c.drawString(70, y, f"{key}: {value}")
            y -= 18

        y -= 15  # Space after each investment

    c.showPage()
    c.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name='investment_comparison_report.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)
