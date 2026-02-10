import os
from flask import Flask, render_template, request
from pykrx import stock  # yfinance 대신 pykrx 사용
import pandas as pd
from datetime import datetime, timedelta

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import HoverTool, ColumnDataSource
from bokeh.layouts import column
from bokeh.resources import INLINE

from backtesting import Backtest, Strategy

app = Flask(__name__)

# --- 1. 전략 클래스 (이전과 동일) ---
class SmaSlopeStrategy(Strategy):
    n1 = 20
    def init(self):
        close = pd.Series(self.data.Close)
        self.sma = self.I(lambda x: x.rolling(self.n1).mean(), close)

    def next(self):
        if len(self.sma) < 3: return
        curr_slope = self.sma[-1] - self.sma[-2]
        prev_slope = self.sma[-2] - self.sma[-3]

        if prev_slope < 0 and curr_slope > 0:
            if not self.position: self.buy()
        elif prev_slope > 0 and curr_slope < 0:
            if self.position: self.position.close()

@app.route('/', methods=['GET', 'POST'])
def index():
    today = datetime.now().strftime('%Y%m%d')
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')

    # 기본값: 삼성전자(005930)
    ticker = request.form.get('ticker', '005930')
    from_date = request.form.get('from_date', one_year_ago).replace('-', '')
    to_date = request.form.get('to_date', today).replace('-', '')

    try:
        # --- 2. pykrx로 데이터 가져오기 ---
        df = stock.get_market_ohlcv_by_date(from_date, to_date, ticker)
        
        if df.empty:
            return render_template('index.html', div="데이터를 찾을 수 없습니다. 종목코드를 확인하세요.", ticker=ticker, resources=INLINE.render())

        # [중요] 한글 컬럼명을 backtesting.py용 영문으로 변경
        df = df.rename(columns={
            '시가': 'Open',
            '고가': 'High',
            '저가': 'Low',
            '종가': 'Close',
            '거래량': 'Volume'
        })
        
        # 인덱스 이름 확인 및 정렬
        df.index.name = 'Date'
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]

        # 3. 백테스트 실행
        bt = Backtest(df, SmaSlopeStrategy, cash=1000000, commission=.002)
        stats = bt.run()
        
        # 4. Bokeh용 데이터 가공
        plot_df = df.reset_index()
        plot_df['SMA20'] = plot_df['Close'].rolling(window=20).mean()
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
            trade_source = ColumnDataSource(trades)

        # 5. 차트 구성
        # P1: 주가
        p1 = figure(title=f"K-Stock ({ticker}) 분석 - SMA 20 기울기 전략", x_axis_type='datetime', 
                    height=400, sizing_mode='stretch_width', tools="pan,wheel_zoom,box_zoom,reset,save")
        w = 12 * 60 * 60 * 1000
        p1.segment('Date', 'High', 'Date', 'Low', color="black", source=source)
        candle_r = p1.vbar('Date', w, 'Open', 'Close', fill_color='color', line_color='color', source=source, alpha=0.5)
        p1.line('Date', 'SMA20', source=source, color='orange', line_width=2, legend_label="SMA 20")
        p1.add_tools(HoverTool(renderers=[candle_r], tooltips=[("날짜", "@Date{%F}"), ("종가", "@Close{0,0}")], 
                               formatters={'@Date': 'datetime'}, mode='vline'))
        p1.xaxis.visible = False

        # P2: 자산 및 타점
        p2 = figure(x_axis_type='datetime', x_range=p1.x_range, height=250, title="Equity & Trade Points", sizing_mode='stretch_width')
        equity_line = p2.line('Date', 'Equity', source=equity_source, color='blue', line_width=2)
        if not trades.empty:
            buy_m = p2.scatter(x='EntryTime', y='EntryEquity', size=15, color="#2ecc71", marker="triangle", source=trade_source)
            sell_m = p2.scatter(x='ExitTime', y='ExitEquity', size=15, color="#e74c3c", marker="inverted_triangle", source=trade_source)
            p2.add_tools(HoverTool(renderers=[buy_m, sell_m], tooltips="""
                <div style="background: #2c3e50; color: white; padding: 5px;">
                    <b>[매매 정보]</b><br>
                    진입: @EntryTime{%F}<br>
                    청산: @ExitTime{%F}<br>
                    수익률: @ReturnPct{0.00%}
                </div>""", formatters={'@EntryTime': 'datetime', '@ExitTime': 'datetime'}, mode='mouse', attachment='above'))
        
        p2.add_tools(HoverTool(renderers=[equity_line], tooltips=[("날짜", "@Date{%F}"), ("자산", "@Equity{0,0}")], 
                               formatters={'@Date': 'datetime'}, mode='vline', attachment='left'))
        p2.xaxis.visible = False

        # P3: 건별 손익
        p3 = figure(x_axis_type='datetime', x_range=p1.x_range, height=180, title="Profit / Loss per Trade", sizing_mode='stretch_width')
        if not trades.empty:
            pl_bar = p3.vbar(x='ExitTime', width=w*2, top='PnL', color='pl_color', source=trade_source)
            p3.add_tools(HoverTool(renderers=[pl_bar], tooltips=[("청산일", "@ExitTime{%F}"), ("손익", "@PnL{0,0}")], 
                                   formatters={'@ExitTime': 'datetime'}, mode='vline'))

        # 6. 결과 전송
        layout = column(p1, p2, p3, sizing_mode='stretch_width')
        script, div = components(layout)
        summary = {"Return": f"{stats['Return [%]']:.2f}%", "WinRate": f"{stats['Win Rate [%]']:.2f}%", "Trades": len(trades)}

        return render_template('index.html', script=script, div=div, ticker=ticker, 
                               from_date=request.form.get('from_date', one_year_ago), 
                               to_date=request.form.get('to_date', today), resources=INLINE.render(), stats=summary)

    except Exception as e:
        return render_template('index.html', div=f"에러: {e}", resources=INLINE.render())

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)