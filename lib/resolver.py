# *      Copyright (C) 2011 Libor Zoubek
# *
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
# */

import sys
import os
import re
import traceback

import util

sys.path.append(os.path.join(os.path.dirname(__file__), 'server'))

RESOLVERS = []
util.debug('%s searching for modules' % __name__)
for module in os.listdir(os.path.join(os.path.dirname(__file__), 'server')):
    if module == '__init__.py' or module[-3:] != '.py':
        continue
    module = module[:-3]
    exec 'import %s' % module
    resolver = eval(module)
    util.debug('found %s %s' % (resolver, dir(resolver)))

    if not hasattr(resolver, '__priority__'):
        resolver.__priority__ = 0
    RESOLVERS.append(resolver)
    del module
RESOLVERS = sorted(RESOLVERS, key=lambda m: -m.__priority__)
util.debug('done')


def item():
    return {'name': '', 'url': '', 'quality': '???', 'surl': '', 'subs': '', 'headers': {}}


def resolve(url):
    """
        resolves given url by asking all resolvers

        returns None if no resolver advised to be able to resolve this url
        returns False if resolver did his job, but did not return any value (thus failed)
        returns Array of resolved objects in positive usecase
    """
    url = util.decode_html(url)
    util.info('Resolving ' + url)
    resolver = _get_resolver(url)
    value = None
    if resolver is None:
        return None
    util.info('Using resolver \'%s\'' % str(resolver.__name__));
    try:
        value = resolver.resolve(url)
    except:
        traceback.print_exc()
    if value is None:
        return False
    default = item()

    def fix_stream(i, url, resolver, default):
        """ fix  missing but required values """
        if 'name' not in i.keys():
            i['name'] = resolver.__name__
        if 'surl' not in i.keys():
            i['surl'] = url
        for key in default.keys():
            if key not in i.keys():
                i[key] = default[key]

    [fix_stream(i, url, resolver, default) for i in value]
    return sorted(value, key=lambda i: i['quality'])


def _get_resolver(url):
    util.debug('Get resolver for ' + url)
    for r in RESOLVERS:
        util.debug('querying %s' % r)
        if r.supports(url):
            return r


def can_resolve(url):
    """ Returns true if we are able to resolve stream by given URL """
    return _get_resolver(url) is not None


def filter_resolvable(url):
    if url.find('facebook') > 0 or url.find('yield') > 0:
        return
    return url.strip('\'\"')


def findstreams(data, regexes=None):
    """
    Finds streams in given data. Respects caller add-on settings about
    quality and asks user if necessary.

    :param data: A string (piece of text / HTML code) or an array of URLs
    :param regexes: An array of strings - regular expressions, each MUST define
                    named group called 'url', which retrieves resolvable URL
                    (that one is passed to resolve operation); only used
                    with 'data' of type 'string'
    :returns: An array of resolved objects, None if at least 1 resolver failed
              to resolve and nothing else was found, an empty array if no
              resolvers for URLs has been found or False if none of regexes
              found anything
    """
    urls = []
    resolvables = []
    resolved = []
    not_found = False
    if isinstance(data, basestring) and regexes:
        for regex in regexes:
            for match in re.finditer(regex, data, re.IGNORECASE | re.DOTALL):
                urls.append(match.group('url'))
    elif isinstance(data, list):
        urls = data
    else:
        raise TypeError
    for url in urls:
        url = filter_resolvable(url)
        if url and url not in resolvables:
            util.info('Found resolvable ' + url)
            resolvables.append(url)
    if len(resolvables) == 0:
        util.info('No resolvables found!')
        return False
    for url in resolvables:
        streams = resolve(url)
        if streams is None:
            util.info('No resolver found for ' + url)
            not_found = True
        elif not streams:
            util.info('There was an error resolving ' + url)
        else:
            if len(streams) > 0:
                for stream in streams:
                    resolved.append(stream)
    if len(resolved) == 0:
        if not_found:
            return []
        return None
    resolved = sorted(resolved, key=lambda i: i['quality'])
    resolved = sorted(resolved, key=lambda i: len(i['quality']))
    resolved.reverse()
    return resolved


q_map = {'3': '720p', '4': '480p', '5': '360p'}


def filter_by_quality(resolved, q):
    util.info('filtering by quality setting ' + q)
    if q == '0':
        return resolved
    sources = {}
    ret = []
    # first group streams by source url
    for item in resolved:
        if item['surl'] in sources.keys():
            sources[item['surl']].append(item)
        else:
            sources[item['surl']] = [item]
    if q == '1':
        # always return best quality from each source
        for key in sources.keys():
            ret.append(sources[key][0])
    elif q == '2':
        # always return worse quality from each source
        for key in sources.keys():
            ret.append(sources[key][-1])
    else:
        # we try to select sources of desired qualities
        quality = q_map[q]
        # 3,4,5 are 720,480,360
        for key in sources.keys():
            added = False
            for item in sources[key]:
                if quality == item['quality']:
                    ret.append(item)
                    added = True
            if not added:
                util.debug('Desired quality %s not found, adding best found' % quality)
                ret.append(sources[key][-1])
    # sort results again, so best quality streams appear first
    ret = sorted(ret, key=lambda i: i['quality'])
    if not q == '2':
        ret.reverse()
    return ret


def findstreams_multi(data, regexes):
    """
    Finds streams in given data according to given regexes
    respects caller addon's setting about desired quality, asks user if needed
    assumes, that all resolvables need to be returned, but in particular quality
    @param data piece of text (HTML code) to search in
    @param regexes - array of strings - regular expressions, each MUST define named group called 'url'
    which retrieves resolvable URL (that one is passsed to resolve operation)
    @return array of dictionaries with keys: name,url,quality,surl
    @return None if at least 1 resoler failed to resolve and nothing else has been found
    @return [] if no resolvable URLs or no resolvers for URL has been found
    """
    resolved = []
    # keep list of found urls to aviod having duplicates
    urls = []
    error = False
    for regex in regexes:
        for match in re.finditer(regex, data, re.IGNORECASE | re.DOTALL):
            print 'Found resolvable %s ' % match.group('url')
            streams = resolve(match.group('url'))
            if isinstance(streams, list) and streams:
                util.debug('There was an error resolving ' + match.group('url'))
                error = True
            if streams is not None:
                if len(streams) > 0:
                    for stream in streams:
                        resolved.append(stream)
    if error and len(resolved) == 0:
        return None
    if len(resolved) == 0:
        return []
    resolved = sorted(resolved, key=lambda i: i['quality'])
    resolved = sorted(resolved, key=lambda i: len(i['quality']))
    resolved2 = resolved
    resolved2.reverse()
    qualities = {}
    for item in resolved2:
        if item['quality'] in qualities.keys():
            qualities[item['quality']].append(item)
        else:
            qualities[item['quality']] = [item]
    # now .. we must sort items to be in same order as they were found on page
    for q in qualities.keys():
        qualities[q] = sorted(qualities[q], key=lambda i: resolved.index(i))
    return qualities
