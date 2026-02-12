import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover

# --- 지표 계산용 보조 함수들 ---
def SMA(values, n):
    return pd.Series(values).rolling(n).mean()

def RSI(values, n=14):
    delta = pd.Series(values).diff()
    gain = (delta.where(delta > 0, 0)).rolling(n).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(n).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def MACD(values, n_fast=12, n_slow=26, n_signal=9):
    fast_ema = pd.Series(values).ewm(span=n_fast).mean()
    slow_ema = pd.Series(values).ewm(span=n_slow).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=n_signal).mean()
    return macd_line, signal_line

# --- 복합 전략 클래스 ---
class ComplexTrendStrategy(Strategy):
    # 최적화를 고려한 파라미터 설정
    n_sma = 200
    n_rsi = 14
    n_macd_f = 12
    n_macd_s = 26
    n_macd_sig = 9

    def init(self):
        # 1. 200일 이동평균선
        self.sma200 = self.I(SMA, self.data.Close, self.n_sma)
        
        # 2. RSI (14)
        self.rsi = self.I(RSI, self.data.Close, self.n_rsi)
        
        # 3. MACD 라인과 시그널 라인
        # self.I가 여러 값을 반환할 때는 튜플로 묶어서 관리
        self.macd, self.signal = self.I(MACD, self.data.Close, 
                                        self.n_macd_f, self.n_macd_s, self.n_macd_sig)

    def next(self):
        # 가격이 200일 이평선 위에 있는지 확인 (장기 상승 추세)
        price_above_sma = self.data.Close[-1] > self.sma200[-1]
        
        # RSI가 50 ~ 60 사이인지 확인 (적당한 매수세)
        rsi_in_range = 50 <= self.rsi[-1] <= 60
        
        # MACD 골든크로스 발생 여부 (MACD가 Signal을 상향 돌파)
        macd_golden_cross = crossover(self.macd, self.signal)

        # 모든 조건 충족 시 매수
        if price_above_sma and rsi_in_range and macd_golden_cross:
            if not self.position:
                self.buy()

        # 매도 조건 (예: MACD 데드크로스 발생 시 수익 실현/손절)
        elif crossover(self.signal, self.macd):
            if self.position:
                self.position.close()