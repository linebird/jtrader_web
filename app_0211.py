from flask import Flask, render_template, request
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import HoverTool, ColumnDataSource
from bokeh.layouts import column
from bokeh.resources import INLINE

from backtesting import Backtest, Strategy

app = Flask(__name__)

# --- 1. 전략 클래스 (SMA 기울기 전략) ---
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
    # --- 2. 날짜 입력값 처리 ---
    # 초기 접속 시 기본값: 최근 1년
    default_to = datetime.now().strftime('%Y-%m-%d')
    default_from = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    # HTML 폼에서 입력받은 값 (없으면 기본값 사용)
    ticker = request.form.get('ticker', '005930')
    html_from_date = request.form.get('from_date', default_from)
    html_to_date = request.form.get('to_date', default_to)

    # pykrx용 날짜 형식 변환 (YYYY-MM-DD -> YYYYMMDD)
    pykrx_from = html_from_date.replace('-', '')
    pykrx_to = html_to_date.replace('-', '')

    try:
        # --- 3. pykrx 데이터 가져오기 ---
        df = stock.get_market_ohlcv_by_date(pykrx_from, pykrx_to, ticker)
        
        if df.empty:
            return render_template('index.html', div="데이터가 없습니다. 종목코드나 기간을 확인하세요.", 
                                   ticker=ticker, from_date=html_from_date, to_date=html_to_date, resources=INLINE.render())

        # 한글 컬럼명 -> 영문 변환
        df = df.rename(columns={'시가':'Open', '고가':'High', '저가':'Low', '종가':'Close', '거래량':'Volume'})
        df.index.name = 'Date'

        # --- 4. 백테스트 실행 ---
        bt = Backtest(df, SmaSlopeStrategy, cash=1000000, commission=.002)
        stats = bt.run()
        
        # --- 5. Bokeh 차트 데이터 준비 ---
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

        # --- 6. 차트 구성 (P1, P2, P3 연동 및 툴팁) ---
        # P1: 주가 차트
        p1 = figure(title=f"K-Stock ({ticker}) 분석 차트", x_axis_type='datetime', 
                    height=400, sizing_mode='stretch_width', tools="pan,wheel_zoom,box_zoom,reset,save")
        w = 12 * 60 * 60 * 1000
        p1.segment('Date', 'High', 'Date', 'Low', color="black", source=source)
        candle_r = p1.vbar('Date', w, 'Open', 'Close', fill_color='color', line_color='color', source=source, alpha=0.5)
        p1.line('Date', 'SMA20', source=source, color='orange', line_width=2, legend_label="SMA 20")
        
        p1.add_tools(HoverTool(renderers=[candle_r], tooltips=[("날짜", "@Date{%F}"), ("종가", "@Close{0,0}")], 
                               formatters={'@Date': 'datetime'}, mode='vline'))
        p1.xaxis.visible = False

        # P2: 자산 곡선 및 매매 타점
        p2 = figure(x_axis_type='datetime', x_range=p1.x_range, height=280, title="자산 변화 및 매매 타점", sizing_mode='stretch_width')
        equity_line = p2.line('Date', 'Equity', source=equity_source, color='blue', line_width=2, legend_label="Equity")

        if not trades.empty:
            buy_m = p2.scatter(x='EntryTime', y='EntryEquity', size=15, color="#2ecc71", marker="triangle", source=trade_source)
            sell_m = p2.scatter(x='ExitTime', y='ExitEquity', size=15, color="#e74c3c", marker="inverted_triangle", source=trade_source)

            # 매매 타점 전용 툴팁 (기존 HTML 디자인 유지)
            p2.add_tools(HoverTool(
                renderers=[buy_m, sell_m],
                tooltips="""
                <div style="background: #2c3e50; color: white; padding: 8px; border-radius: 4px;">
                    <b style="color: #f1c40f;">[매매 상세]</b><br>
                    진입: @EntryTime{%F}<br>
                    청산: @ExitTime{%F}<br>
                    수익률: <b style="color: #2ecc71;">@ReturnPct{0.00%}</b><br>
                    손익: $@PnL{0,0}
                </div>""", 
                formatters={'@EntryTime': 'datetime', '@ExitTime': 'datetime'}, mode='mouse', attachment='above'
            ))

        p2.add_tools(HoverTool(renderers=[equity_line], tooltips=[("날짜", "@Date{%F}"), ("자산", "$@Equity{0,0}")], 
                               formatters={'@Date': 'datetime'}, mode='vline', attachment='left'))
        p2.xaxis.visible = False

        # P3: 건별 손익
        p3 = figure(x_axis_type='datetime', x_range=p1.x_range, height=180, title="건별 손익(P/L)", sizing_mode='stretch_width')
        if not trades.empty:
            pl_bar = p3.vbar(x='ExitTime', width=w*2, top='PnL', color='pl_color', source=trade_source)
            p3.add_tools(HoverTool(renderers=[pl_bar], tooltips=[("청산일", "@ExitTime{%F}"), ("손익", "$@PnL{0,0}")], 
                                   formatters={'@ExitTime': 'datetime'}, mode='vline'))

        # --- 7. 결과 전송 ---
        layout = column(p1, p2, p3, sizing_mode='stretch_width')
        script, div = components(layout)
        summary = {"Return": f"{stats['Return [%]']:.2f}%", "WinRate": f"{stats['Win Rate [%]']:.2f}%", "Trades": len(trades)}

        return render_template('index.html', script=script, div=div, ticker=ticker, 
                               from_date=html_from_date, to_date=html_to_date, resources=INLINE.render(), stats=summary)

    except Exception as e:
        return render_template('index.html', div=f"에러 발생: {e}", resources=INLINE.render(), 
                               ticker=ticker, from_date=html_from_date, to_date=html_to_date)

if __name__ == '__main__':
    app.run(debug=True)