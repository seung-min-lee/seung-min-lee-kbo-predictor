import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
df = pd.read_csv('kbo_verify_log.csv')
print('컬럼:', list(df.columns))
print(df.tail(10).to_string())
