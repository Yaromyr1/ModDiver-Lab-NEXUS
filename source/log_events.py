"""Log levels that remain compatible with existing string callbacks."""
import re


class Message(str):
    def __new__(cls, text, level='info'):
        value=super().__new__(cls,str(text));value.level=level
        return value


def classify(text):
    if hasattr(text,'level'):return text.level
    value=str(text).strip().lower()
    if 'steam verification:' in value or 'steam verify requested : granted' in value:return 'info_blue'
    if re.match(r'^preview complete: \d+ file\(s\) would be installed; 0 failed/skipped\.', value):return 'success'
    if re.search(r'\berror\b|\bfailed\b|could not|traceback|\bexception\b|\baborted\b|\brefused\b',value):return 'error'
    if value == 'repaired and updated succesfully':return 'success'
    if value == 'built-in mods repaired/updated successfully':return 'success'
    if value == 'nothing deployed' or value == 'completely purged the mod library; game files and deployment backups were not changed':return 'success'
    if re.match(r'(deployed [1-9]\d* file|deployment complete|installed |updated to |restored/removed [1-9])',value):return 'success'
    if 'warning' in value or 'skipped' in value or 'fallback' in value:return 'warning'
    return 'info'


def emit(log,text,level):
    log(Message(text,level))
