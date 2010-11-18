"""
A Python client for the New York Times Congress API
"""
__author__ = "Chris Amico (eyeseast@gmail.com)"
__version__ = "0.1.0"

import datetime
import httplib2
import os
import urllib

try:
    import json
except ImportError:
    import simplejson as json

__all__ = ('NytCongress', 'NytCongressError', 'get_congress')

DEBUG = False

def get_congress(year):
    "Return the Congress number for a given year"
    return (year - 1789) / 2 + 1

def parse_date(s):
    """
    Parse a date using dateutil.parser.parse if available,
    falling back to datetime.datetime.strptime if not
    """
    if isinstance(s, (datetime.datetime, datetime.date)):
        return s
    try:
        from dateutil.parser import parse
    except ImportError:
        parse = lambda d: datetime.datetime.strptime(d, "%Y-%m-%d")
    return parse(s)

CURRENT_CONGRESS = get_congress(datetime.datetime.now().year)

class NytCongressError(Exception):
    """
    Exception for New York Times Congress API errors
    """

class Client(object):

    BASE_URI = "http://api.nytimes.com/svc/politics/v3/us/legislative/congress/"
    
    def __init__(self, apikey, cache='.cache'):
        self.apikey = apikey
        self.http = httplib2.Http(cache)
    
    def fetch(self, path, *args, **kwargs):
        parse = kwargs.pop('parse', lambda r: r['results'][0])
        kwargs['api-key'] = self.apikey
        
        if not path.lower().startswith(self.BASE_URI):
            url = self.BASE_URI + "%s.json?" % path
            url = (url % args) + urllib.urlencode(kwargs)
        else:
            url = path + '?' + urllib.urlencode(kwargs)
            
        resp, content = self.http.request(url)
        result = json.loads(content)
        
        if callable(parse):
            result = parse(result)
            if DEBUG:
                result['_url'] = url
        return result
        
class MembersClient(Client):
    
    def get(self, member_id):
        "Takes a bioguide_id, returns a legislator"
        path = "members/%s"
        result = self.fetch(path, member_id)
        return result
    
    def filter(self, chamber, congress=CURRENT_CONGRESS, **kwargs):
        "Takes a chamber, Congress, and optional state and district, returning a list of members"
        path = "%s/%s/members"
        result = self.fetch(path, congress, chamber, **kwargs)
        return result
    
    def bills(self, member_id, type='introduced'):
        "Same as BillsClient.by_member"
        path = "members/%s/bills/%s"
        result = self.fetch(path, member_id, type)
        return result

class BillsClient(Client):
    
    def by_member(self, member_id, type='introduced'):
        "Takes a bioguide ID and a type (introduced|updated|cosponsored|withdrawn), returns recent bills"
        path = "members/%s/bills/%s"
        result = self.fetch(path, member_id, type)
        return result
    
    def get(self, bill_id, congress=CURRENT_CONGRESS):
        path = "%s/bills/%s"
        result = self.fetch(path, congress, bill_id)
        return result
    
    def amendments(self, bill_id, congress=CURRENT_CONGRESS):
        path = "%s/bills/%s/amendments"
        result = self.fetch(path, congress, bill_id)
        return result
    
    def related(self, bill_id, congress=CURRENT_CONGRESS):
        path = "%s/bills/%s/related"
        result = self.fetch(path, congress, bill_id)
        return result
    
    def subjects(self, bill_id, congress=CURRENT_CONGRESS):
        path = "%s/bills/%s/subjects"
        result = self.fetch(path, congress, bill_id)
        return result
    
    def recent(self, chamber, congress=CURRENT_CONGRESS, type='introduced'):
        "Takes a chamber, Congress, and type (introduced|updated), returns a list of recent bills"
        path = "%s/%s/bills/%s"
        result = self.fetch(path, congress, chamber, type)
        return result
    
    def introduced(self, chamber, congress=CURRENT_CONGRESS):
        "Shortcut for getting introduced bills"
        return self.recent(chamber, congress, 'introduced')
    
    def updated(self, chamber, congress=CURRENT_CONGRESS):
        "Shortcut for getting updated bills"
        return self.recent(chamber, congress, 'updated')

class VotesClient(Client):
    
    # date-based queries
    def by_month(self, chamber, year=None, month=None):
        """
        Return votes for a single month, defaulting to the current month.
        """
        if not str(chamber).lower() in ('house', 'senate'):
            raise TypeError("by_month() requires chamber, year and month. Got %s, %s, %s" \
                % (chamber, year, month))

        now = datetime.datetime.now()
        year = year or now.year
        month = month or now.month

        path = "%s/votes/%s/%s"
        result = self.fetch(path, chamber, year, month, parse=lambda r: r['results'])
        return result
    
    def by_range(self, chamber, start, end):
        """\
        Return votes cast in a chamber between two dates,
        up to one month apart.
        """
        start, end = parse_date(start), parse_date(end)
        if start > end:
            start, end = end, start
        format = "%Y-%m-%d"
        path = "%s/votes/%s/%s"
        result = self.fetch(path, chamber, start.strftime(format), end.strftime(format), 
            parse=lambda r: r['results'])
        return result
    
    def by_date(self, chamber, date):
        "Return votes cast in a chamber on a single day"
        date = parse_date(date)
        return self.by_range(chamber, date, date)
    
    def today(self, chamber):
        "Return today's votes in a given chamber"
        now = datetime.date.today()
        return self.by_range(chamber, now, now)
    
    # detail response
    def get(self, chamber, rollcall_num, session, congress=CURRENT_CONGRESS):
        path = "%s/%s/sessions/%s/votes/%s"
        result = self.fetch(path, congress, chamber, session, rollcall_num,
            parse=lambda r: r['results'])
        return result
        

class CommitteesClient(Client):
    
    def filter(self, chamber, congress=CURRENT_CONGRESS):
        path = "%s/%s/committees"
        result = self.fetch(path, congress, chamber)
        return result
    
    def get(self, chamber, committee_id, congress=CURRENT_CONGRESS):
        path = "%s/%s/committees/%s"
        result = self.fetch(path, congress, chamber, committee_id)
        return result

class NytCongress(Client):
    """
    Implements the public interface for the NYT Congress API
    
    Methods are namespaced by topic (though some have multiple access points).
    Everything returns decoded JSON, with fat trimmed.
    
    In addition, the top-level namespace is itself a client, which
    can be used to fetch generic resources, using the API URIs included
    in responses. This is here so you don't have to write separate
    functions that add on your API key and trim fat off responses.
    
    Create a new instance with your API key, or set an environment
    variable called NYT_CONGRESS_API_KEY.
    
    NytCongress uses httplib2, and caching is pluggable. By default,
    it uses httplib2.FileCache, in a directory called .cache, but it
    should also work with memcache or anything else that exposes the
    same interface as FileCache (per httplib2 docs).
    """
    
    def __init__(self, apikey=os.environ.get('NYT_CONGRESS_API_KEY'), cache='.cache'):
        super(NytCongress, self).__init__(apikey, cache)
        self.members = MembersClient(self.apikey, cache)
        self.bills = BillsClient(self.apikey, cache)
        self.committees = CommitteesClient(self.apikey, cache)
        self.votes = VotesClient(self.apikey, cache)
    

