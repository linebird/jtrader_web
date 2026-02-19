from flask import Blueprint, render_template, request
from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.layouts import column
from bokeh.resources import INLINE
from bokeh.models import HoverTool, ColumnDataSource
from backtesting import Backtest

# --- [중요] 전략 모듈 임포트 ---
from strategies.macd_strategy import MACD_Indicator, MacdStrategy
from strategies.sma_strategies import SmaSlopeStrategy, SmaCrossStrategy
from strategies.custom_strategies import ComplexTrendStrategy
from strategies.adx_strategy import AdxStrategy, ADX_Indicator   # ADX 전략 임포트

# 전략 매핑 딕셔너리 (임포트한 클래스 사용)
STRATEGIES = {
    'slope': SmaSlopeStrategy,
    'cross': SmaCrossStrategy,
    'complex': ComplexTrendStrategy,
    'adx': AdxStrategy,
    'macd': MacdStrategy
}

# 1. 블루프린트 생성 (이름: stock, URL 접두사 설정을 위해 사용)
stock_bp = Blueprint('stock', __name__)


@stock_bp.route('/', methods=['GET', 'POST'])
def index():
    # ... (날짜 설정 로직은 이전과 동일) ...
    default_to = datetime.now().strftime('%Y-%m-%d')
    default_from = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    # ticker = request.form.get('ticker', '005930')
    # 1. 우선순위: GET 파라미터(?ticker=...) -> POST 폼 데이터 -> 기본값(삼성전자)
    ticker = request.args.get('ticker') or request.form.get('ticker', '005930')
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
        # 차트 표시용 ADX 계산
        adx_vals, p_di, m_di = ADX_Indicator(plot_df['High'], plot_df['Low'], plot_df['Close'])
        plot_df['ADX'], plot_df['PlusDI'], plot_df['MinusDI'] = adx_vals, p_di, m_di
        # plot_df에 MACD 지표 추가 (차트 출력용)
        m_line, s_line, h_bar = MACD_Indicator(plot_df['Close'])
        plot_df['MACD'], plot_df['MACD_Signal'], plot_df['MACD_Hist'] = m_line, s_line, h_bar

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

        if strat_name == 'adx':
            p4 = figure(x_axis_type='datetime', x_range=p1.x_range, height=180, title="ADX 지표", sizing_mode='stretch_width')
            p4.line('Date', 'ADX', source=source, color='purple', legend_label="ADX")
            p4.line('Date', 'PlusDI', source=source, color='green', legend_label="+DI")
            p4.line('Date', 'MinusDI', source=source, color='red', legend_label="-DI")
            p4.legend.location = "top_left"
            layout = column(p1, p2, p3, p4, sizing_mode='stretch_width')
        elif strat_name == 'macd':
            # --- [추가] P4: MACD 전용 차트 ---
            p4 = figure(x_axis_type='datetime', x_range=p1.x_range, height=200, 
                        title="MACD 지표", sizing_mode='stretch_width')
            
            p4.line('Date', 'MACD', source=source, color='blue', line_width=1.5, legend_label="MACD")
            p4.line('Date', 'MACD_Signal', source=source, color='orange', line_width=1.5, legend_label="Signal")
            
            # MACD 히스토그램 (막대)
            p4.vbar('Date', w, top='MACD_Hist', source=source, color='gray', alpha=0.5, legend_label="Histogram")
            
            p4.add_tools(HoverTool(tooltips=[
                ("MACD", "@MACD{0.00}"), ("Signal", "@MACD_Signal{0.00}")
            ], mode='vline'))
            p4.xaxis.visible = False
            p4.legend.location = "top_left"
            p4.legend.orientation = "horizontal"
            layout = column(p1, p2, p4, p3, sizing_mode='stretch_width')
        else:
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

  