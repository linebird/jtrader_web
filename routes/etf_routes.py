from flask import Blueprint, render_template, request
from pykrx import stock
from datetime import datetime, timedelta
import pandas as pd

etf_bp = Blueprint('etf', __name__)

def get_filtered_etfs(date_str, params, retry_days=5):
    """
    pykrx를 이용해 ETF 종목 필터링 수행
    """
    df = pd.DataFrame()
    target_date = date_str
    
    # 주말/공휴일 대비 재시도 로직
    for i in range(retry_days):
        current_attempt_date = (datetime.strptime(target_date, "%Y%m%d") - timedelta(days=i)).strftime("%Y%m%d")
        # ETF 등락 및 특수 지표 가져오기
        df = stock.get_etf_price_change_by_ticker(current_attempt_date, current_attempt_date)
        if not df.empty:
            target_date = current_attempt_date
            break
            
    if df.empty:
        return df, target_date

    df = df.reset_index() # 티커를 컬럼으로
    
    # 종목명 추가
    df['종목명'] = df['티커'].apply(lambda x: stock.get_etf_ticker_name(x))

    # 필터링 조건 적용
    try:
        if params.get('min_change'): df = df[df['등락률'] >= float(params['min_change'])]
        if params.get('max_change'): df = df[df['등락률'] <= float(params['max_change'])]
        if params.get('min_amount'): df = df[df['거래대금'] >= int(params['min_amount'])]
        if params.get('min_volume'): df = df[df['거래량'] >= int(params['min_volume'])]
        if params.get('min_close'): df = df[df['종가'] >= int(params['min_close'])]
        if params.get('max_close'): df = df[df['종가'] <= int(params['max_close'])]
        
    except ValueError:
        pass

    # 등락률 내림차순 정렬
    df = df.sort_values(by='등락률', ascending=False)
    
    return df, target_date

@etf_bp.route('/etf', methods=['GET', 'POST'])
def etf_list():
    default_date = datetime.now().strftime("%Y-%m-%d")
    
    if request.method == 'POST':
        date_input = request.form.get('date', default_date).replace('-', '')
        params = {
            'min_change': request.form.get('min_change'),
            'max_change': request.form.get('max_change'),
            'min_amount': request.form.get('min_amount'),
            'min_volume': request.form.get('min_volume'),
            'min_close': request.form.get('min_close'),
            'max_close': request.form.get('max_close')
        }
    else:
        date_input = default_date.replace('-', '')
        params = {
            'min_amount': '500000000',
            'min_volume': '100000',
            'min_change': '0',
            'min_close': '10000'
        }

    df, final_date = get_filtered_etfs(date_input, params)
    
    etfs_data = []
    if not df.empty:
        # 1. 컬럼명을 안전하게 강제 변환 (문자열 포함 여부 확인)
        new_cols = {}
        for col in df.columns:
            if '티커' in col: new_cols[col] = 'ticker'
            elif '종목명' in col: new_cols[col] = 'name'
            elif '시가' in col: new_cols[col] = 'open'
            elif '종가' in col: new_cols[col] = 'close'
            elif '등락률' in col: new_cols[col] = 'change_rate'
            elif '거래대금' in col: new_cols[col] = 'amount'
            elif '거래량' in col: new_cols[col] = 'volume'
        
        df = df.rename(columns=new_cols)

        # 2. 필수 컬럼이 누락되었을 경우를 대비해 기본값 생성 (방어적 코딩)
        required_cols = ['ticker', 'name', 'open', 'close', 'change_rate', 'amount', 'volume']
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0  # 만약 gap이 없으면 0으로 가득 찬 컬럼이라도 생성

        # 3. 결측치 처리 및 리스트 변환
        df = df.fillna(0)
        etfs_data = df.to_dict('records')

    # 총 건수 계산
    total_count = len(etfs_data)

    return render_template('etf.html', 
                           etfs=etfs_data, 
                           total_count=total_count, 
                           date=datetime.strptime(final_date, "%Y%m%d").strftime("%Y-%m-%d"),
                           params=params)