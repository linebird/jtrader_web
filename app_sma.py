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
from backtesting.lib import crossover

app = Flask(__name__)

# --- 1. 전략 정의 ---
class SmaCross(Strategy):
    n1 = 20
    n2 = 60
    def init(self):
        close = pd.Series(self.data.Close)
        self.sma1 = self.I(lambda x: x.rolling(self.n1).mean(), close)
        self.sma2 = self.I(lambda x: x.rolling(self.n2).mean(), close)
    def next(self):
        if crossover(self.sma1, self.sma2):
            self.buy()
        elif crossover(self.sma2, self.sma1):
            self.position.close()

@app.route('/', methods=['GET', 'POST'])
def index():
    # 날짜 초기값
    today = datetime.now().strftime('%Y-%m-%d')
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    ticker_symbol = request.form.get('ticker', 'AAPL').upper()
    from_date = request.form.get('from_date', one_year_ago)
    to_date = request.form.get('to_date', today)

    try:
        # 2. 데이터 다운로드
        df = yf.download(ticker_symbol, start=from_date, end=to_date)
        if df.empty:
            return render_template('index.html', div="데이터 없음", ticker=ticker_symbol, resources=INLINE.render())
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 3. 백테스트 실행
        bt = Backtest(df, SmaCross, cash=100000, commission=.002)
        stats = bt.run()
        
        # 4. 데이터 가공 (시간대 제거 및 지표 계산)
        plot_df = df.reset_index()
        if plot_df['Date'].dt.tz is not None:
            plot_df['Date'] = plot_df['Date'].dt.tz_localize(None)
        
        plot_df['SMA20'] = plot_df['Close'].rolling(window=20).mean()
        plot_df['SMA60'] = plot_df['Close'].rolling(window=60).mean()
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

        # --- 5. 차트 생성 - P1: 주가 및 이평선 ---
        p1 = figure(title=f"{ticker_symbol} 주가 및 지표", x_axis_type='datetime', 
                    height=450, sizing_mode='stretch_width', tools="pan,wheel_zoom,box_zoom,reset,save")
        
        w = 12 * 60 * 60 * 1000
        p1.segment('Date', 'High', 'Date', 'Low', color="black", source=source)
        candle_r = p1.vbar('Date', w, 'Open', 'Close', fill_color='color', line_color='color', source=source, alpha=0.6)
        
        sma20_r = p1.line('Date', 'SMA20', source=source, color='orange', line_width=2, legend_label="SMA 20")
        sma60_r = p1.line('Date', 'SMA60', source=source, color='purple', line_width=2, legend_label="SMA 60")

        # P1 전용 툴팁 복구
        hover_candle = HoverTool(renderers=[candle_r], tooltips=[
            ("날짜", "@Date{%F}"), ("시가", "@Open{0,0.00}"), ("종가", "@Close{0,0.00}"), ("거래량", "@Volume{0,0}")
        ], formatters={'@Date': 'datetime'}, mode='vline')
        
        hover_sma = HoverTool(renderers=[sma20_r, sma60_r], tooltips=[
            ("이평선", "$name"), ("가격", "$y{0,0.00}")
        ], mode='vline')

        p1.add_tools(hover_candle, hover_sma)
        p1.xaxis.visible = False
        p1.legend.click_policy = "hide"
        p1.legend.location = "top_left"

        # --- 6. 차트 생성 - P2: 자산 곡선 및 매매 타점 ---
        p2 = figure(x_axis_type='datetime', x_range=p1.x_range, height=280, 
                    title="자산 현황 및 매매 타점", sizing_mode='stretch_width')
        
        equity_line = p2.line('Date', 'Equity', source=equity_source, color='blue', line_width=2, legend_label="잔고(Equity)")

        if not trades.empty:
            buy_m = p2.scatter(x='EntryTime', y='EntryEquity', size=15, color="#2ecc71", marker="triangle", legend_label="매수", source=trade_source)
            sell_m = p2.scatter(x='ExitTime', y='ExitEquity', size=15, color="#e74c3c", marker="inverted_triangle", legend_label="매도", source=trade_source)

            # 매매 타점 전용 툴팁 (우선순위 상단)
            hover_trade = HoverTool(
                renderers=[buy_m, sell_m],
                tooltips="""
                <div style="background-color: #2c3e50; color: white; padding: 8px; border-radius: 4px;">
                    <b style="color: #f1c40f;">[매매 상세]</b><br>
                    진입: @EntryTime{%F}<br>
                    청산: @ExitTime{%F}<br>
                    수익률: <b style="color: #2ecc71;">@ReturnPct{0.00%}</b><br>
                    수익금: $@PnL{0,0}
                </div>
                """,
                formatters={'@EntryTime': 'datetime', '@ExitTime': 'datetime'},
                mode='mouse', attachment='above'
            )
            p2.add_tools(hover_trade)

        # 자산 곡선 툴팁
        hover_equity = HoverTool(renderers=[equity_line], tooltips=[
            ("날짜", "@Date{%F}"), ("자산", "$@Equity{0,0}")
        ], formatters={'@Date': 'datetime'}, mode='vline', attachment='left')
        p2.add_tools(hover_equity)
        p2.xaxis.visible = False

        # --- 7. 차트 생성 - P3: 건별 손익 ---
        p3 = figure(x_axis_type='datetime', x_range=p1.x_range, height=150, title="건별 손익(P/L)", sizing_mode='stretch_width')
        if not trades.empty:
            p3.vbar(x='ExitTime', width=w*2, top='PnL', color='pl_color', source=trade_source)
            p3.add_tools(HoverTool(tooltips=[("청산일", "@ExitTime{%F}"), ("손익", "$@PnL{0,0}")], 
                                   formatters={'@ExitTime': 'datetime'}, mode='vline'))

        # 8. 레이아웃
        layout = column(p1, p2, p3, sizing_mode='stretch_width')
        script, div = components(layout)

        summary = {
            "Return": f"{stats['Return [%]']:.2f}%",
            "WinRate": f"{stats['Win Rate [%]']:.2f}%",
            "Trades": len(trades)
        }

        return render_template('index.html', script=script, div=div, ticker=ticker_symbol, 
                               from_date=from_date, to_date=to_date, resources=INLINE.render(), stats=summary)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return render_template('index.html', div=f"에러: {e}", resources=INLINE.render())

if __name__ == '__main__':
    app.run(debug=True)