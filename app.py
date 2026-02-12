import os
from flask import Flask, render_template, request
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import HoverTool, ColumnDataSource
from bokeh.layouts import column
from bokeh.resources import INLINE

from backtesting import Backtest

# --- [중요] 전략 모듈 임포트 ---
from strategies.sma_strategies import SmaSlopeStrategy, SmaCrossStrategy
from strategies.custom_strategies import ComplexTrendStrategy

app = Flask(__name__)

# 전략 매핑 딕셔너리 (임포트한 클래스 사용)
STRATEGIES = {
    'slope': SmaSlopeStrategy,
    'cross': SmaCrossStrategy,
    'complex': ComplexTrendStrategy
}

@app.route('/', methods=['GET', 'POST'])
def index():
    # ... (날짜 설정 로직은 이전과 동일) ...
    default_to = datetime.now().strftime('%Y-%m-%d')
    default_from = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    ticker = request.form.get('ticker', '005930')
    html_from_date = request.form.get('from_date', default_from)
    html_to_date = request.form.get('to_date', default_to)
    strat_name = request.form.get('strategy', 'slope')
    
    # 선택된 전략 클래스 할당
    selected_strat = STRATEGIES.get(strat_name, SmaSlopeStrategy)

    try:
        # 1. 데이터 가져오기 (pykrx)
        pykrx_from = html_from_date.replace('-', '')
        pykrx_to = html_to_date.replace('-', '')
        df = stock.get_market_ohlcv_by_date(pykrx_from, pykrx_to, ticker)
        
        if df.empty:
            return render_template('index.html', div="데이터 없음", ticker=ticker, from_date=html_from_date, to_date=html_to_date, strategy=strat_name, resources=INLINE.render())

        df = df.rename(columns={'시가':'Open', '고가':'High', '저가':'Low', '종가':'Close', '거래량':'Volume'})
        df.index.name = 'Date'

        # 2. 백테스트 실행 (임포트된 전략 클래스 적용)
        bt = Backtest(df, selected_strat, cash=1000000, commission=.002)
        stats = bt.run()
        
        # 3. 차트용 데이터 가공 (기존 로직 100% 동일)
        plot_df = df.reset_index()
        plot_df['SMA20'] = plot_df['Close'].rolling(window=20).mean()
        plot_df['SMA200'] = plot_df['Close'].rolling(window=200).mean()
        if strat_name == 'cross':
            plot_df['SMA5'] = plot_df['Close'].rolling(window=5).mean()
        plot_df['color'] = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(plot_df.Open, plot_df.Close)]
        source = ColumnDataSource(plot_df)

        equity_df = stats['_equity_curve'].reset_index()
        equity_source = ColumnDataSource(equity_df)
        
        trades = stats['_trades'].copy()
        if not trades.empty:
            equity_map = equity_df.set_index('Date')['Equity']
            trades['EntryEquity'] = trades['EntryTime'].map(equity_map)
            trades['ExitEquity'] = trades['ExitTime'].map(equity_map)
            trades['pl_color'] = ["#26a69a" if p > 0 else "#ef5350" for p in trades['PnL']]
            # [2, 2] 패턴 추가
            trades['dash_pattern'] = [(2, 2)] * len(trades)
            trade_source = ColumnDataSource(trades)

        # 4. Bokeh 차트 구성 (기존과 동일하게 모든 툴팁/마커 유지)
        p1 = figure(title=f"K-Stock ({ticker}) - {strat_name.upper()} 전략 분석", x_axis_type='datetime', 
                    height=400, sizing_mode='stretch_width', tools="pan,wheel_zoom,box_zoom,reset,save")
        w = 12 * 60 * 60 * 1000
        p1.segment('Date', 'High', 'Date', 'Low', color="black", source=source)
        candle_r = p1.vbar('Date', w, 'Open', 'Close', fill_color='color', line_color='color', source=source, alpha=0.5)
        
        p1.line('Date', 'SMA20', source=source, color='orange', line_width=2, legend_label="SMA 20")
        if strat_name == 'cross':
            p1.line('Date', 'SMA5', source=source, color='blue', line_width=1.5, legend_label="SMA 5")
        p1.line('Date', 'SMA200', source=source, color='red', line_dash='dashed', legend_label="SMA 200")
        
        # 매매 연결선 (파이프 점선 패턴 적용)
        if not trades.empty:
            p1.segment(x0='EntryTime', y0='EntryPrice', x1='ExitTime', y1='ExitPrice',
                       line_dash='dash_pattern', line_color='#7f8c8d', line_width=1.5,
                       source=trade_source, legend_label="매매 연결선")

        # ... (이후 툴팁 및 P2, P3 생성 로직은 이전과 완전히 동일) ...
        # (지면 관계상 생략하지만, 기존의 p1.add_tools, p2, p3 코드를 그대로 넣으시면 됩니다)
        
        # [생략된 부분 예시]
        p1.add_tools(HoverTool(renderers=[candle_r], tooltips=[("날짜", "@Date{%F}"), ("종가", "@Close{0,0}")], 
                               formatters={'@Date': 'datetime'}, mode='vline'))
        p1.xaxis.visible = False

        p2 = figure(x_axis_type='datetime', x_range=p1.x_range, height=280, title="자산 변화 및 매매 타점", sizing_mode='stretch_width')
        equity_line = p2.line('Date', 'Equity', source=equity_source, color='blue', line_width=2, legend_label="Equity")

        if not trades.empty:
            buy_m = p2.scatter(x='EntryTime', y='EntryEquity', size=15, color="#2ecc71", marker="triangle", source=trade_source)
            sell_m = p2.scatter(x='ExitTime', y='ExitEquity', size=15, color="#e74c3c", marker="inverted_triangle", source=trade_source)
            p2.add_tools(HoverTool(renderers=[buy_m, sell_m], tooltips="""
                <div style="background: #2c3e50; color: white; padding: 8px; border-radius: 4px;">
                    <b style="color: #f1c40f;">[매매 상세]</b><br>
                    진입: @EntryTime{%F}<br>
                    청산: @ExitTime{%F}<br>
                    수익률: <b style="color: #2ecc71;">@ReturnPct{0.00%}</b><br>
                    손익: $@PnL{0,0}
                </div>""", formatters={'@EntryTime': 'datetime', '@ExitTime': 'datetime'}, mode='mouse', attachment='above'))

        p2.add_tools(HoverTool(renderers=[equity_line], tooltips=[("날짜", "@Date{%F}"), ("자산", "$@Equity{0,0}")], 
                               formatters={'@Date': 'datetime'}, mode='vline', attachment='left'))
        p2.xaxis.visible = False

        p3 = figure(x_axis_type='datetime', x_range=p1.x_range, height=180, title="건별 손익(P/L)", sizing_mode='stretch_width')
        if not trades.empty:
            pl_bar = p3.vbar(x='ExitTime', width=w*2, top='PnL', color='pl_color', source=trade_source)
            p3.add_tools(HoverTool(renderers=[pl_bar], tooltips=[("청산일", "@ExitTime{%F}"), ("손익", "$@PnL{0,0}")], 
                                   formatters={'@ExitTime': 'datetime'}, mode='vline'))

        layout = column(p1, p2, p3, sizing_mode='stretch_width')
        script, div = components(layout)
        summary = {"Return": f"{stats['Return [%]']:.2f}%", "WinRate": f"{stats['Win Rate [%]']:.2f}%", "Trades": len(trades)}

        return render_template('index.html', script=script, div=div, ticker=ticker, 
                               from_date=html_from_date, to_date=html_to_date, strategy=strat_name,
                               resources=INLINE.render(), stats=summary)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return render_template('index.html', div=f"에러: {e}", resources=INLINE.render(), 
                               ticker=ticker, from_date=html_from_date, to_date=html_to_date, strategy=strat_name)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host='0.0.0.0', port=port)