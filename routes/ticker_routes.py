from flask import Blueprint, render_template, request
from pykrx import stock
from datetime import datetime, timedelta
import pandas as pd

ticker_bp = Blueprint('ticker', __name__)

def get_filtered_tickers(date_str, params, retry_days=5):
    """
    pykrx를 이용해 종목 필터링 수행
    """
    df = pd.DataFrame()
    target_date = date_str
    
    # 데이터가 없을 경우(주말/공휴일) 재시도 로직
    for i in range(retry_days):
        current_attempt_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=i)).strftime("%Y%m%d")
        df = stock.get_market_price_change(current_attempt_date, current_attempt_date)
        if not df.empty:
            target_date = current_attempt_date
            break
            
    if df.empty:
        return df, target_date

    # 인덱스(티커)를 컬럼으로 변환하고 종목명 추가
    df = df.reset_index()
    
    # 필터링 조건 적용 (사용자 입력값이 있을 경우에만)
    try:
        if params.get('min_close'): df = df[df['종가'] >= int(params['min_close'])]
        if params.get('max_close'): df = df[df['종가'] <= int(params['max_close'])]
        
        if params.get('min_volume'): df = df[df['거래량'] >= int(params['min_volume'])]
        if params.get('max_volume'): df = df[df['거래량'] <= int(params['max_volume'])]
        
        if params.get('min_amount'): df = df[df['거래대금'] >= int(params['min_amount'])]
        if params.get('max_amount'): df = df[df['거래대금'] <= int(params['max_amount'])]
        
        if params.get('min_change'): df = df[df['등락률'] >= float(params['min_change'])]
        if params.get('max_change'): df = df[df['등락률'] <= float(params['max_change'])]
    except ValueError:
        pass # 숫자 변환 에러 시 해당 필터 무시

    # 등락률 기준 내림차순 정렬
    df = df.sort_values(by='등락률', ascending=False)
    
    return df, target_date

@ticker_bp.route('/ticker', methods=['GET', 'POST'])
def ticker_list():
    # 오늘 날짜 기준 기본값
    default_date = datetime.now().strftime("%Y-%m-%d")
    
    if request.method == 'POST':
        date_input = request.form.get('date', default_date).replace('-', '')
        params = {
            'min_close': request.form.get('min_close'),
            'max_close': request.form.get('max_close'),
            'min_volume': request.form.get('min_volume'),
            'max_volume': request.form.get('max_volume'),
            'min_amount': request.form.get('min_amount'),
            'max_amount': request.form.get('max_amount'),
            'min_change': request.form.get('min_change'),
            'max_change': request.form.get('max_change'),
        }
    else:
        # GET 요청 시 빈 결과 혹은 기본값 필터링
        date_input = default_date.replace('-', '')
        params = {
            'min_close': '3000',            # 3000원 이상 종가
            'max_close': '200000',           # 20만원 이하 종가
            'min_amount': '100000000000', # 1000억 이상 거래대금
            'min_change': '-5',             # 0% 이상 등락률
            'min_volume': '20000000',       # 2000만 이상 거래량
        } 

    df, final_date = get_filtered_tickers(date_input, params)
    
    # 결과를 리스트 형태로 변환하여 템플릿에 전달
    tickers_data = df.to_dict('records') if not df.empty else []
    
    return render_template('ticker.html', 
                           tickers=tickers_data, 
                           date=datetime.strptime(final_date, "%Y%m%d").strftime("%Y-%m-%d"),
                           params=params)