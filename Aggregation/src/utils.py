from datetime import datetime

def convert_str_to_datetime(dt_string):
    return datetime.strptime(dt_string,'%Y-%m-%dT%H:%M:%S')

def convert_datetime_to_str(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%S')