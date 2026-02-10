from flask import Flask, render_template, request
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import HoverTool, ColumnDataSource
from bokeh.layouts import column
from bokeh.resources import INLINE

from backtesting import Backtest, Strategy

app = Flask(__name__)

# --- 1. 새로운 전략 클래스 정의 (이평선 기울기 반전) ---
class SmaSlopeStrategy(Strategy):
    n1 = 20  # 이동평균 기간

    def init(self):
        # 20일 이동평균 계산 (self.I를 사용하여 지표 등록)
        close = pd.Series(self.data.Close)
        self.sma = self.I(lambda x: x.rolling(self.n1).mean(), close)

    def next(self):
        # 데이터가 충분하지 않으면 패스
        if len(self.sma) < 3:
            return

        # 기울기 계산: (현재 값 - 이전 값)
        curr_slope = self.sma[-1] - self.sma[-2]
        prev_slope = self.sma[-2] - self.sma[-3]

        # 매수 조건: 기울기가 음수에서 양수로 전환될 때 (하락 후 반등)
        if prev_slope < 0 and curr_slope > 0:
            if not self.position:
                self.buy()

        # 매도 조건: 기울기가 양수에서 음수로 전환될 때 (상승 후 꺾임)
        elif prev_slope > 0 and curr_slope < 0:
            if self.position:
                self.position.close()

@app.route('/', methods=['GET', 'POST'])
def index():
    today = datetime.now().strftime('%Y-%m-%d')
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    # 사용자 입력 받기
    ticker_input = request.form.get('ticker', '005930') # 기본값 삼성전자
    from_date = request.form.get('from_date', one_year_ago)
    to_date = request.form.get('to_date', today)

    try:
        # --- 2. 데이터 가져오기 및 전처리 ---
        # 한국 종목일 경우 자동으로 .KS를 붙이거나 입력된 티커 그대로 사용
        ticker = ticker_input.upper()
        if ticker.isdigit(): # 숫자만 입력된 경우 한국 종목으로 간주
            search_ticker = f"{ticker}.KS"
        else:
            search_ticker = ticker

        df = yf.download(search_ticker, start=from_date, end=to_date)
        
        if df.empty:
            return render_template('index.html', div="데이터가 없습니다.", ticker=ticker_input, resources=INLINE.render())

        # MultiIndex 컬럼 정리 (제안해주신 코드 적용)
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

        # --- 3. 백테스트 실행 ---
        bt = Backtest(df, SmaSlopeStrategy, cash=1000000, commission=.002)
        stats = bt.run()
        
        # 4. 차트 데이터 준비
        plot_df = df.reset_index()
        if plot_df['Date'].dt.tz is not None:
            plot_df['Date'] = plot_df['Date'].dt.tz_localize(None)
        
        # 전략 지표(SMA 20) 계산
        plot_df['SMA20'] = plot_df['Close'].rolling(window=20).mean()
        plot_df['color'] = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(plot_df.Open, plot_df.Close)]
        source = ColumnDataSource(plot_df)

        equity_df = stats['_equity_curve'].reset_index()
        if equity_df['Date'].dt.tz is not None:
            equity_df['Date'] = equity_df['Date'].dt.tz_localize(None)
        equity_source = ColumnDataSource(equity_df)
        
        trades = stats['_trades'].copy()
        if not trades.empty:
            trades['EntryTime'] = trades['EntryTime'].dt.tz_localize(None)
            trades['ExitTime'] = trades['ExitTime'].dt.tz_localize(None)
            equity_map = equity_df.set_index('Date')['Equity']
            trades['EntryEquity'] = trades['EntryTime'].map(equity_map)
            trades['ExitEquity'] = trades['ExitTime'].map(equity_map)
            trades['pl_color'] = ["#26a69a" if p > 0 else "#ef5350" for p in trades['PnL']]
            trade_source = ColumnDataSource(trades)

        # --- 5. Bokeh 차트 구성 ---
        
        # P1: 주가 및 SMA 20
        p1 = figure(title=f"{search_ticker} 분석 (SMA 20 기울기 반전 전략)", x_axis_type='datetime', 
                    height=400, sizing_mode='stretch_width', tools="pan,wheel_zoom,box_zoom,reset,save")
        
        w = 12 * 60 * 60 * 1000
        p1.segment('Date', 'High', 'Date', 'Low', color="black", source=source)
        candle_r = p1.vbar('Date', w, 'Open', 'Close', fill_color='color', line_color='color', source=source, alpha=0.5)
        
        # 전략의 기준선인 SMA 20만 표시
        sma_r = p1.line('Date', 'SMA20', source=source, color='orange', line_width=2.5, legend_label="SMA 20")

        # P1 툴팁
        p1.add_tools(HoverTool(renderers=[candle_r], tooltips=[
            ("날짜", "@Date{%F}"), ("종가", "@Close{0,0.00}"), ("거래량", "@Volume{0,0}")
        ], formatters={'@Date': 'datetime'}, mode='vline'))
        p1.xaxis.visible = False

        # P2: 자산 곡선 및 매매 타점
        p2 = figure(x_axis_type='datetime', x_range=p1.x_range, height=280, 
                    title="자산 현황 및 매매 타점", sizing_mode='stretch_width')
        
        equity_line = p2.line('Date', 'Equity', source=equity_source, color='blue', line_width=2, legend_label="Equity")

        if not trades.empty:
            buy_m = p2.scatter(x='EntryTime', y='EntryEquity', size=15, color="#2ecc71", marker="triangle", legend_label="Buy", source=trade_source)
            sell_m = p2.scatter(x='ExitTime', y='ExitEquity', size=15, color="#e74c3c", marker="inverted_triangle", legend_label="Sell", source=trade_source)

            # 매매 정보 전용 툴팁 (상단 고정)
            p2.add_tools(HoverTool(
                renderers=[buy_m, sell_m],
                tooltips="""
                <div style="background-color: #2c3e50; color: white; padding: 8px; border-radius: 4px;">
                    <b style="color: #f1c40f;">[매매 결과]</b><br>
                    진입: @EntryTime{%F} (@EntryPrice{0,0.00})<br>
                    청산: @ExitTime{%F} (@ExitPrice{0,0.00})<br>
                    수익률: <b style="color: #2ecc71;">@ReturnPct{0.00%}</b>
                </div>
                """,
                formatters={'@EntryTime': 'datetime', '@ExitTime': 'datetime'},
                mode='mouse', attachment='above'
            ))

        # 잔고 툴팁
        p2.add_tools(HoverTool(renderers=[equity_line], tooltips=[("날짜", "@Date{%F}"), ("자산", "$@Equity{0,0}")], 
                               formatters={'@Date': 'datetime'}, mode='vline', attachment='left'))
        p2.xaxis.visible = False

        # P3: 건별 손익
        p3 = figure(x_axis_type='datetime', x_range=p1.x_range, height=150, title="Trade Profit / Loss", sizing_mode='stretch_width')
        if not trades.empty:
            p3.vbar(x='ExitTime', width=w*2, top='PnL', color='pl_color', source=trade_source)

        # 레이아웃 생성
        layout = column(p1, p2, p3, sizing_mode='stretch_width')
        script, div = components(layout)

        summary = {
            "Return": f"{stats['Return [%]']:.2f}%",
            "WinRate": f"{stats['Win Rate [%]']:.2f}%",
            "Trades": len(trades)
        }

        return render_template('index.html', script=script, div=div, ticker=ticker_input, 
                               from_date=from_date, to_date=to_date, resources=INLINE.render(), stats=summary)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return render_template('index.html', div=f"에러: {e}", resources=INLINE.render())

if __name__ == '__main__':
    app.run(debug=True)