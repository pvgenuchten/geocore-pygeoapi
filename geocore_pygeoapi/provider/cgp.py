import os
import json
import codecs
import logging
from re import compile
from datetime import datetime

import requests

from pygeoapi import l10n
from pygeoapi.provider.base import (
    BaseProvider,
    ProviderQueryError,
    ProviderConnectionError,
    ProviderNoDataError,
    ProviderInvalidQueryError,
    ProviderItemNotFoundError
)

JSON_REGEX = {
    'posix': compile(r'("\\"\\".+?\\"\\"")'),
    'nt': compile(r'("\"\".+?\"\"")')
}
DATE_REGEX = compile(r'(\d{4})-?(\d{0,2})-?(\d{0,2})[T| ]?(\d{0,2}):?(\d{0,2}):?(\d{0,2})')  # noqa

LOGGER = logging.getLogger(__name__)


class GeoCoreProvider(BaseProvider):
    """ Provider for the Canadian Federal Geospatial Platform (FGP).

    Queries NRCan's geoCore API.
    """

    def __init__(self, provider_def, requested_locale=None):
        super().__init__(provider_def, requested_locale)

        LOGGER.debug('setting geoCore base URL')
        try:
            url = self.data['base_url']
        except KeyError:
            raise RuntimeError(
                f'missing base_url setting in {self.name} provider data'
            )
        else:
            # sanitize trailing slashes
            self._baseurl = f'{url.rstrip("/")}/'

        LOGGER.debug('map endpoints to provider methods')
        mapping = self.data.get('mapping', {})
        if not mapping:
            LOGGER.warning(f'No endpoint mapping found for {self.name} provider: using defaults')  # noqa
        self._query_url = f'{self._baseurl}{mapping.get(self.query.__name__, "geo")}'  # noqa
        self._get_url = f'{self._baseurl}{mapping.get(self.get.__name__, "id")}'

        LOGGER.debug('get queryable field info')
        self.fields = self.data.get('queryables', {})
        LOGGER.debug(f'Queryables: {self.fields}')

    @property
    def _iswin(self):
        """ Returns True if the interpreter runs on Windows. """
        return os.name == 'nt'

    @property
    def _getregex(self):
        """ Returns the compiled regex pattern for JSON strings
        suitable for the current platform (POSIX or Windows). """
        return JSON_REGEX[os.name]

    def _parse_json(self, body):
        """ Parses the geoCore response body as a JSON object. """

        def unescape(match):
            """ Unescape string and replace double quotes with single ones. """
            unescaped = codecs.escape_decode(match.group(0))[0].decode()  # noqa
            if not self._iswin:
                unescaped = unescaped.replace('\\', '')
            return unescaped.replace('""', '"').strip('"')

        result = {}
        if not body:
            return result

        # geoCore returns some JSON array values as encoded JSON strings
        # Python's JSON loader does not like them, so we have to replace those
        LOGGER.debug('parse JSON response body')
        json_str = self._getregex.sub(unescape, body)
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as err:
            LOGGER.error('Failed to parse JSON response', exc_info=err)
            return result

        # check if geoCore's response has Items or an error
        if 'Items' not in result:
            error = result.get('errorMessage', 'missing Items object')
            raise ProviderInvalidQueryError(error)

        return result

    @staticmethod
    def _asisodate(value):
        """ Returns an ISO formatted timestamp (with Z suffix) from a string.
        If the given value can't be turned into a date, `None` will be returned.
        """
        try:
            matches = DATE_REGEX.match(value)
            dt = datetime(*(int(i) if i else 1 for i in matches.groups()))
        except (ValueError, TypeError, AttributeError):
            return None
        if dt.year == 1:
            # Treat dates like "0001-01-01" as an invalid date
            return None
        return f'{dt.isoformat()}Z'

    def _request_json(self, url, params):
        """ Performs a GET request on `url` and returns the JSON response. """
        response = None
        if 'lang' not in params and self.locale:
            # Add language parameter, if missing (geoCore wants ISO 639-1 codes)  # noqa
            LOGGER.debug(f"Requesting geoCore response in '{self.locale.language}'")  # noqa
            params['lang'] = self.locale.language
        try:
            response = requests.get(url, params)
            response.raise_for_status()
        except requests.HTTPError as err:
            LOGGER.error(err)
            raise ProviderQueryError(
                f'failed to query {response.url if response else url}')
        except requests.ConnectionError as err:
            LOGGER.error(err)
            raise ProviderConnectionError(
                f'failed to connect to {response.url if response else url}')

        return self._parse_json(response.text)

    @staticmethod
    def _getcoords(item):
        """ Removes the 'coordinates' value from a JSON item and parses it. """
        coords = item.pop('coordinates', [])
        if isinstance(coords, list):
            return coords
        try:
            return json.loads(coords)
        except json.JSONDecodeError as err:
            LOGGER.warning(f'failed to parse coords: {err}')
        return []

    @staticmethod
    def _aslist(value, delim=','):
        """ Converts a `delim`-separated string `value` into a list. """
        return [v.strip() for v in (value or '').split(delim) if v.strip()]

    @staticmethod
    def _asdict(value, item_delim=',', pair_delim='='):
        """ Converts string `value` into a dictionary if possible.

        :param value:       The string value to convert.
        :param item_delim:  The delimiter used to separate dict items.
        :param pair_delim:  The delimiter used to separate key-value pairs.
        """
        if not value or pair_delim not in value:
            return {}
        return {
            k.strip(): v.strip()
            for k, v in (
                p.split(pair_delim)[:2]
                for p in value.strip('{}').split(item_delim)
            )
        }

    @staticmethod
    def _getbbox(coords):
        """ Creates a bounding box array from a coordinate list. """
        minx = float('NaN')
        miny = float('NaN')
        maxx = float('NaN')
        maxy = float('NaN')
        for part in coords:
            for x, y in part:
                minx = min(x, minx)
                miny = min(y, miny)
                maxx = max(x, maxx)
                maxy = max(y, maxy)
        return [minx, miny, maxx, maxy]

    def _gettimerange(self, temporal):
        """ Converts a temporal extent string into a list of [begin, end]. """
        t_extent = self._asdict(temporal)
        begin = self._asisodate(t_extent.get('begin'))
        end = self._asisodate(t_extent.get('end'))
        return [begin, end]

    def _getextent(self, coords, temporal):
        """ Returns an OGC-API records spatial and temporal extent object.

        :param coords:      A coordinate list.
        :param temporal:    A temporal extent string formatted as
                            "{begin=YYYY-MM-DD, end=YYYY-MM_DD}".
        :returns:           An OGC-API GeoJSON extent dict.
        """

        bbox = self._getbbox(coords)
        interval = self._gettimerange(temporal)

        return {
            'spatial': {
                'bbox': [[bbox]],
                'crs': 'http://www.opengis.net/def/crs/OGC/1.3/CRS84'
            },
            'temporal': {
                'interval': interval,
                'trs': 'http://www.opengis.net/def/uom/ISO-8601/0/Gregorian'
            }
        }

    def _to_geojson(self, json_obj, skip_geometry=False, single_feature=False):
        """ Turns a regular geoCore JSON object into GeoJSON. """
        features = []
        num_matched = None

        for item in json_obj.get('Items', []):
            feature = {
                'type': 'Feature',
                'geometry': None
            }

            # Get ID and validate it
            id_ = item.pop('id', None)
            if id_ is None:
                LOGGER.warning(f'skipped record without ID')
                continue
            feature['id'] = id_
            item['externalId'] = id_

            # Pop 'total' value for numberMatched property (for paging)
            num_matched = int(item.pop('total', 0))

            # Rename and set/fix date properties
            date_created = self._asisodate(item.get('created'))
            date_updated = self._asisodate(item.pop('published', None))
            item['record-created'] = date_created
            item['record-updated'] = date_updated
            item['created'] = date_created
            item['updated'] = date_updated

            # Convert keywords to an array
            item['keywords'] = self._aslist(item.get('keywords'))

            # Get coordinates and set geometry and extent
            coords = self._getcoords(item)
            if coords:
                if skip_geometry:
                    LOGGER.debug('skipped geometry')
                else:
                    # Add Polygon geometry to feature
                    feature['geometry'] = {
                        'type': 'Polygon',
                        'coordinates': coords
                    }

                # Add extent object to feature
                item['extent'] = self._getextent(
                    coords,
                    item.pop('temporalExtent', None)
                )
            else:
                LOGGER.debug('record has no coordinates: '
                             'cannot set geometry and extent')

            # Remove options and convert to associations
            options = item.pop('options', [])
            for opt in options:
                url = opt.get('url')
                title = l10n.translate(opt.get('name'), self.locale)
                type_ = opt.get('protocol')
                rel = 'item'
                i18n = self.locale
                desc = l10n.translate(opt.get('description'), self.locale)
                if desc and desc.count(';') == 2:
                    # TODO: retrieve mime type from URL or lookup
                    rel, type_, i18n = desc.split(';')
                if not (type_ and url):
                    # Do not add links without a type or URL
                    continue
                lnk = {
                    'href': url,
                    'type': type_,
                    'rel': rel,
                    'title': title,
                    'hreflang': l10n.locale2str(i18n) if
                    isinstance(i18n, l10n.Locale) else i18n
                }
                item.setdefault('associations', []).append(lnk)

            # Remove graphicOverview and promote/set first thumbnailUrl
            try:
                url = item.pop('graphicOverview')[0].get('overviewfilename')
                item['thumbnailUrl'] = url
            except (KeyError, IndexError, AttributeError):
                LOGGER.warning('could not find overview thumbnail')

            # Set properties and add to feature list
            feature['properties'] = item
            features.append(feature)

        if features and single_feature == 1:
            LOGGER.debug('returning single feature')
            return features[0]

        LOGGER.debug('returning feature collection')
        collection = {
            'type': 'FeatureCollection',
            'features': features,
            'numberReturned': len(features)
        }
        LOGGER.debug(f'provider said there are {num_matched} matches')
        if num_matched:
            collection['numberMatched'] = num_matched
        return collection

    def query(self, startindex=0, limit=10, resulttype='results',
              bbox=[], datetime_=None, properties=[], sortby=[],
              select_properties=[], skip_geometry=False, q=None):
        """
        Performs a geoCore search.

        :param startindex: starting record to return (default 0)
        :param limit: number of records to return (default 10)
        :param resulttype: return results or hit limit (default results)
        :param bbox: bounding box [minx,miny,maxx,maxy]
        :param datetime_: temporal (datestamp or extent)
        :param properties: list of tuples (name, value)
        :param sortby: list of dicts (property, order)
        :param select_properties: list of property names
        :param skip_geometry: bool of whether to skip geometry (default False)
        :param q: full-text search term(s)

        :returns: dict of 0..n GeoJSON features
        """
        params = {}

        if resulttype != 'results':
            # Supporting 'hits' will require a change on the geoCore API
            LOGGER.warning(f'Unsupported resulttype {resulttype}: '
                           f'defaulting to "results"')

        if bbox:
            LOGGER.debug('processing bbox parameter')
            minx, miny, maxx, maxy = bbox
            params['east'] = minx
            params['west'] = maxx
            params['north'] = maxy
            params['south'] = miny
        else:
            LOGGER.debug('set keyword_only search')
            params['keyword_only'] = 'true'

        # Set min and max (1-based!)
        LOGGER.debug('set query limits')
        params['min'] = startindex + 1
        params['max'] = startindex + limit

        # Set queryables
        if properties:
            LOGGER.debug(f'Adding queryables: {properties}')
            for k, v in properties:
                params[k] = v

        # Set text-based search
        if q:
            LOGGER.debug(f'Adding free-text search: {q}')
            params['keyword'] = q

        LOGGER.debug(f'querying {self._query_url}')
        json_obj = self._request_json(self._query_url, params)

        LOGGER.debug('turn geoCore JSON into GeoJSON')
        return self._to_geojson(json_obj, skip_geometry)

    def get(self, identifier):
        """ Request a single geoCore record by ID.

        :param identifier:  The ID of the record to retrieve.

        :returns:   dict containing 1 GeoJSON feature
        :raises:    ProviderItemNotFoundError if identifier was not found
        """
        params = {
            'id': identifier
        }

        LOGGER.debug(f'querying {self._get_url}')
        json_obj = self._request_json(self._get_url, params)

        if not json_obj.get('Items', []):
            raise ProviderItemNotFoundError(f'record id {identifier} not found')

        LOGGER.debug('turn geoCore JSON into GeoJSON')
        return self._to_geojson(json_obj, single_feature=True)

    def __repr__(self):
        return f'<{self.__class__.__name__}> {self.data}'
