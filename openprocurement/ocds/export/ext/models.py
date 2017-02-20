from openprocurement.ocds.export.models import (
    Award,
    Tender,
    Contract,
    Item,
    Value,
    Model,
    Unit,
    Document,
    callbacks,
    modelsMap,
    Release,

)
from openprocurement.ocds.export.helpers import (
    convert_bids,
    create_auction,
    convert_unit_and_location,
    convert_cancellation,
    convert_questions,
    unique_documents,
    build_package
)


callbacks['bids'] = lambda raw_data: convert_bids(raw_data.get('bids'))
callbacks['auctions'] = lambda raw_data: create_auction(raw_data)
callbacks['items'] = lambda raw_data: convert_unit_and_location(raw_data.get('items'))
callbacks['tender'] = lambda raw_data: convert_cancellation(raw_data)
callbacks['enquiries'] = lambda raw_data: convert_questions(raw_data)
callbacks['currentStage'] = lambda raw_data: raw_data.get('status')
callbacks['documents'] = lambda raw_data: unique_documents(raw_data.get('documents'), extension=True)


class TenderExt(Tender):

    __slots__ = Tender.__slots__ + (
        'auctions',
        'tenderID',
        'pendingCancellation',
        'enquiries',
        'lots',
        'procurementMethodType',
        'currentStage',
    )


class AwardExt(Award):

    __slots__ = Award.__slots__ + (
        'lotID',
    )


class ValueExt(Value):

    __slots__ = Value.__slots__ + (
        'valueAddedTaxIncluded',
    )


class Bid(Model):

    __slots__ = (
        'id',
        'date',
        'status',
        'tenderers',
        'value',
        'documents',
        'relatedLot',
        'participationUrl'
    )


class ContractExt(Contract):

    __slots__ = Contract.__slots__ + (
        'suppliers',
        'contractID',
        'contractNumber',
    )


class Auction(Model):

    __slots__ = (
        'url',
        'period',
        'minimalStep',
        'relatedLot',
    )


class UnitExt(Unit):

    __slots__ = Unit.__slots__ + (
        'id',
        'symbol',
        'scheme',
    )


class Location(Model):

    __slots__ = (
        "geomerty",
    )


class ItemExt(Item):

    __slots__ = Item.__slots__ + (
        'deliveryAddress',
        'deliveryLocation',
        'relatedLot',
        'deliveryDate'
    )


class Geometry(Model):

    __slots__ = (
        'coordinates',
    )


class Enquiry(Model):

    __slots__ = (
        'id',
        'date',
        'author',
        'title',
        'description',
        'answer',
        'dateAnswered',
        'relatedItem',
    )


class DocumentExt(Document):

    __slots__ = Document.__slots__ + (
        'relatedItem',
        'documentScope',
    )


class Lot(Model):

    __slots__ = (
        'status',
        'description',
        'title',
        'value',
        'id',
        'pendingCancellation',
    )


class ReleaseExt(Release):

    __slots__ = Release.__slots__ + (
        'bids',
    )


modelsMap['contracts'] = (ContractExt, [])
modelsMap['auctions'] = (Auction, [])
modelsMap['tender'] = (TenderExt, {})
modelsMap['unit'] = (UnitExt, {})
modelsMap['items'] = (ItemExt, [])
modelsMap['value'] = (ValueExt, {})
modelsMap['enquiries'] = (Enquiry, [])
modelsMap['documents'] = (DocumentExt, [])
modelsMap['lots'] = (Lot, [])
modelsMap['bids'] = (Bid, [])
modelsMap['documents'] = (DocumentExt, [])
modelsMap['awards'] = (AwardExt, [])


def release_tender_ext(tender, prefix):
    release = ReleaseExt(tender, prefix).__export__()
    tag = ['tender']
    for op in ['awards', 'contracts', 'bids']:
        if op in release:
            tag.append(op[:-1])
    release['tag'] = tag
    return release


def package_tenders_ext(tenders, config):
    package = build_package(config)
    package['releases'] = [release_tender_ext(t, config.get('prefix')) for t in tenders]
    return package