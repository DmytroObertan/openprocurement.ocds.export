# -*- coding: utf-8 -*-
import itertools
import simplejson as json
import ocdsmerge
import jsonpatch as jpatch
import gevent
import logging
import os.path
import json
from requests.exceptions import HTTPError
from .exceptions import LBMismatchError
#from ocds.export.release import release_tender, release_tenders
#from ocds.export import release_tender, release_tenders
#from ocds.storage import release_tender, release_tenders
from iso8601 import parse_date
from datetime import datetime
from collections import Counter
from uuid import uuid4
from copy import deepcopy


logger = logging.getLogger(__name__)


def tender_converter(tender):
    """ converts raw openprocurement data into acceptable by OCDS standard """
    if 'bids' in tender:
        tender['tenderers'] = list(itertools.chain.from_iterable(
            map(lambda b: b.get('tenderers', ''), tender['bids'])))

        del tender['numberOfBids']
        del tender['bids']
    elif 'tenderers' not in tender:
        tender['tenderers'] = []
    tender['tenderers'] = unique_tenderers(tender['tenderers'])
    if 'id' in tender:
        tender['_id'] = tender['id']
        del tender['id']

    if 'minimalStep' in tender:
        tender['minValue'] = tender['minimalStep']
        del tender['minimalStep']
    return tender


def unique_tenderers(tenderers):
    """leave only unique tenderers as required by standard"""
    return {t['identifier']['id']: t for t in tenderers}.values() if tenderers else []


def unique_documents(documents):
    """adds `-<number>` to docs with same ids"""
    if not documents:
        return
    cout = Counter(doc['id'] for doc in documents)
    for i in [i for i, c in cout.iteritems() if c > 1]:
        for index, d in enumerate([d for d in documents if d['id'] == i]):
            d['id'] = d['id'] + '-{}'.format(index)


def patch_converter(patch):
    """creates OCDS Amendment dict"""
    return [{'property': op['path'], 'former_value': op.get('value')} for op in patch]


def get_ocid(prefix, tenderID):
    """greates unique contracting identifier"""
    return "{}-{}".format(prefix, tenderID)


def award_converter(tender):
    if 'lots' in tender:
        for award in tender['awards']:
            award['items'] = [item for item in tender['items']
                              if item['relatedLot'] == award['lotID']]
    else:
        for award in tender['awards']:
            award['items'] = tender['items']
    return tender


def encoder(obj):
    if hasattr(obj, 'to_json'):
        return obj.to_json()
    return json.dumps(obj)


def decoder(obj):
    return json.loads(obj)


def get_compiled_release(releases):
    compiled = ocdsmerge.merge(releases)
    if 'bids' in compiled['tender'].keys():
        for bid in compiled['tender']['bids']:
            if 'lotValues' in bid.keys():
                for lotval in bid['lotValues']:
                    del lotval['id']
    return compiled


def generate_uri():
    return 'https://fake-url/tenders-{}'.format(uuid4().hex)


def add_revisions(tenders):
    prev_tender = tenders[0]
    new_tenders = []
    for tender in tenders[1:]:
        patch = jpatch.make_patch(prev_tender, tender)
        tender['revisions'] = list(patch)
        prev_tender = deepcopy(tender)
        new_tenders.append(tender)
        del prev_tender['revisions']
    return new_tenders


def mode_test(tender):
    """ drops all test mode tenders """
    return 'ТЕСТУВАННЯ'.decode('utf-8') not in tender['title']


def now():
    # uri = StringType()
    return parse_date(datetime.now().isoformat()).isoformat()


def get_start_point(forward, backward, cookie, queue,
                    callback=lambda x: x, extra={}):
    forward_params = {'feed': 'changes'}
    backward_params = {'feed': 'changes', 'descending': '1'}
    if extra:
        [x.update(extra) for x in [forward_params, backward_params]]
    r = backward.get_tenders(backward_params)
    if backward.session.cookies != cookie:
        raise LBMismatchError
    backward_params['offset'] = r['next_page']['offset']
    forward_params['offset'] = r['prev_page']['offset']
    queue.put(filter(callback, r['data']))
    return forward_params, backward_params


def fetch_tenders(client, src, dest):
    logger.info('Starting downloading tenders')
    while True:
        for feed in src:
            if not feed:
                continue
            logger.info('Uploading {} tenders'.format(len(feed)))
            resp = client.fetch(feed)
            if resp:
                logger.info('fetched {} tenders'.format(len(resp)))
            dest.put(resp)
        gevent.sleep(0.5)


def fetch_tender_versioned(client, src, dest):
    logger.info('Starting downloading tender')
    while True:
        for feed in src:
            if not feed:
                gevent.sleep(0.5)
                continue

            for _id in [i['id'] for i in feed]:
                tenders = []
                version, tender = client.get_tender(_id)
                tender['_id'] = tender['id']
                tenders.append(tender)
                logger.info('Got tender id={}, version={}'.format(tender['id'], version))
                try:
                    while version != '1':
                        version = str(int(version) - 1)
                        logger.info('Getting prev version = {}'.format(version))
                        version, tender = client.get_tender(_id, version)
                        tenders.append(tender)
                except HTTPError:
                    logger.fatal("Falied to retreive tender id={} \n"
                                 "version {}".format(tender['id'], version))
                    continue
                dest.put(tenders)


def create_releases(prefix, src, dest):
    logger.info('Starting generating releases')
    while True:
        for batch in src:
            logger.info('Got {} tenders'.format(len(batch)))
            for tender in batch:
                try:
                    release = release_tender(tender, prefix)
                    logger.info("generated release for tender "
                                "{}".format(tender['id']))
                    dest.put(release)
                except Exception as e:
                    logger.fatal('Error {} during'
                                 ' generation release'.format(e))
            gevent.sleep(0.5)
        gevent.sleep(2)


def batch_releases(prefix, src, dest):
    logger.info('Starting generating releases')
    while True:
        for batch in src:
            logger.info('Got {} tenders'.format(len(batch)))
            releases = release_tenders(iter(batch), prefix)
            dest.put(releases)
            gevent.sleep(0.5)
        gevent.sleep(2)


def save_items(storage, src, dest):
    logger.info('Start saving')
    while True:
        for item in src:
            for obj in item:
                obj.store(storage)
                logger.info('Saved doc {}'.format(obj['id']))


def exists_or_modified(db, doc):
    if doc['id'] not in db:
        return True
    else:
        if db.get(doc['id'])['dateModified'] < doc['dateModified']:
            return True
    return False