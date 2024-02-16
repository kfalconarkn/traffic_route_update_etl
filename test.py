import pandas as pd

#create empty pandas dataframe
df = pd.DataFrame()

df['duration_start'] = "2016-06-13T12:13:00+10:00"

df['duration_start'] = pd.to_datetime(df['duration_start'], utc=True)

print(df.head())