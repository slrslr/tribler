"""
All conversions for the MultiChain Community.
"""
from struct import pack, unpack_from, calcsize
from Tribler.dispersy.conversion import BinaryConversion
from Tribler.dispersy.message import DropPacket

# Hash length used in the MultiChain Community
HASH_LENGTH = 32
SIG_LENGTH = 64
PK_LENGTH = 74

EMPTY_HASH = '1' * HASH_LENGTH  # Used in a request when the response data is not yet available
GENESIS_ID = '0' * HASH_LENGTH  # ID of the first block of the chain.

# Formatting of the signature packet
# TotalUp TotalDown Sequence_number, previous_hash
append_format = 'Q Q i ' + str(HASH_LENGTH) + 's'
# Up, Down
common_data_format = 'I I'
# [Up, Down,
#  TotalUpRequester, TotalDownRequester, sequence_number_requester, previous_hash_requester,
#  TotalUpResponder, TotalDownResponder, sequence_number_responder, previous_hash_responder]
signature_format = ' '.join(["!", common_data_format, append_format, append_format])
# PK_requester, PK_responder, Up, Down,
# TotalUpRequester, TotalDownRequester, sequence_number_requester, previous_hash_requester, signature_requester
requester_half_format = str(PK_LENGTH) + 's ' + str(PK_LENGTH) + 's ' + common_data_format + \
                        ' ' + append_format + ' ' + str(SIG_LENGTH) + 's '
signature_size = calcsize(signature_format)
append_size = calcsize(append_format)

crawl_request_format = 'i'
crawl_request_size = calcsize(crawl_request_format)

# [signature, pk]
authentication_format = str(PK_LENGTH) + 's ' + str(SIG_LENGTH) + 's '
# [Up, Down, TotalUpRequester, TotalDownRequester, sequence_number_requester, previous_hash_requester,
#   TotalUpResponder, TotalDownResponder, sequence_number_responder, previous_hash_responder,
#   signature_requester, pk_requester, signature_responder, pk_responder]
crawl_response_format = signature_format + authentication_format + authentication_format
crawl_response_size = calcsize(crawl_response_format)


class MultiChainConversion(BinaryConversion):
    """
    Class that handles all encoding and decoding of MultiChain messages.
    """

    def __init__(self, community):
        super(MultiChainConversion, self).__init__(community, "\x01")
        from Tribler.community.multichain.community import SIGNATURE, CRAWL_REQUEST, CRAWL_RESPONSE, CRAWL_RESUME

        # Define Request Signature.
        self.define_meta_message(chr(1), community.get_meta_message(SIGNATURE),
                                 self._encode_signature, self._decode_signature)
        self.define_meta_message(chr(2), community.get_meta_message(CRAWL_REQUEST),
                                 self._encode_crawl_request, self._decode_crawl_request)
        self.define_meta_message(chr(3), community.get_meta_message(CRAWL_RESPONSE),
                                 self._encode_crawl_response, self._decode_crawl_response)
        self.define_meta_message(chr(4), community.get_meta_message(CRAWL_RESUME),
                                 self._encode_crawl_resume, self._decode_crawl_resume)

    @staticmethod
    def _encode_signature(message):
        """
        Encode the signature message
        :param message: Message.impl of SIGNATURE
        :return: encoding ready to be sent of the network.
        """
        payload = message.payload
        return pack(signature_format, *(payload.up, payload.down,
                                        payload.total_up_requester, payload.total_down_requester,
                                        payload.sequence_number_requester, payload.previous_hash_requester,
                                        payload.total_up_responder, payload.total_down_responder,
                                        payload.sequence_number_responder, payload.previous_hash_responder)),

    @staticmethod
    def _decode_signature(placeholder, offset, data):
        """
        Decode an incoming signature message
        :param placeholder:
        :param offset: Start of the SIGNATURE message in the data.
        :param data: ByteStream containing the message.
        :return: (offset, SIGNATURE.impl)
        """
        if len(data) < offset + signature_size:
            raise DropPacket("Unable to decode the payload")

        values = unpack_from(signature_format, data, offset)
        offset += signature_size

        return offset, placeholder.meta.payload.implement(*values)

    @staticmethod
    def _encode_crawl_request(message):
        """
        Encode a crawl request message.
        :param message: Message.impl of CrawlRequestPayload.impl
        return encoding ready to be sent of the network of the message
        """
        return pack(crawl_request_format, message.payload.requested_sequence_number),

    @staticmethod
    def _decode_crawl_request(placeholder, offset, data):
        """
        Decode an incoming crawl request message.
        :param placeholder:
        :param offset: Start of the CrawlRequest message in the data.
        :param data: ByteStream containing the message.
        :return: (offset, CrawlRequest.impl)
        """
        if len(data) < offset + crawl_request_size:
            raise DropPacket("Unable to decode the payload")

        values = unpack_from(crawl_request_format, data, offset)
        offset += crawl_request_size

        return offset, placeholder.meta.payload.implement(*values)

    @staticmethod
    def _encode_crawl_response(message):
        """
        Encode a crawl response message.
        :param message: Message.impl of CrawlResponsePayload.impl
        :return encoding ready to be sent to the network of the message
        """
        payload = message.payload
        return encode_block_crawl(payload),

    @staticmethod
    def _decode_crawl_response(placeholder, offset, data):
        """
        Decode an incoming crawl response message.
        :param placeholder:
        :param offset: Start of the CrawlResponse message in the data.
        :param data: ByteStream containing the message.
        :return: (offset, CrawlResponse.impl)
        """
        if len(data) < offset + crawl_response_size:
            raise DropPacket("Unable to decode the payload")

        values = unpack_from(crawl_response_format, data, offset)
        offset += crawl_response_size

        return offset, placeholder.meta.payload.implement(*values)

    @staticmethod
    def _encode_crawl_resume(message):
        """
        Encode a crawl resume message.
        :param message: Message.impl of CrawlResumePayload.impl
        return encoding of the message ready to be sent over the network
        """
        return '',

    @staticmethod
    def _decode_crawl_resume(placeholder, offset, data):
        """
        Decode an incoming crawl resume message.
        :param placeholder:
        :param offset: Start of the CrawlResume message in the data.
        :param data: ByteStream containing the message.
        :return: (offset, CrawlResume.impl)
        """
        return offset, placeholder.meta.payload.implement()


def split_function(payload):
    """
    This function splits the SIGNATURE MESSAGE in parts.
    The first to be signed by the requester, and the second the whole message to be signed by the responder
    :param payload: Encoded message to be split
    :return: (first_part, whole)
    """
    return payload[:-append_size], payload


def encode_block(payload, requester, responder):
    """
    This function encodes a block.
    :param payload: Payload containing the data as properties, not including the requester and responder data.
    for example a signature request/response payload.
    :param requester: The requester of the block as a dispersy member
    :param responder: The responder of the block as a dispersy member
    :return: encoding
    """
    # Test code sometimes run a different curve with a different key length resulting in hard to catch bugs.
    assert len(requester[1].public_key) == PK_LENGTH
    assert len(responder[1].public_key) == PK_LENGTH
    return pack(crawl_response_format, *(payload.up, payload.down,
                                         payload.total_up_requester, payload.total_down_requester,
                                         payload.sequence_number_requester, payload.previous_hash_requester,
                                         payload.total_up_responder, payload.total_down_responder,
                                         payload.sequence_number_responder, payload.previous_hash_responder,
                                         requester[1].public_key, requester[0],
                                         responder[1].public_key, responder[0]))


def encode_block_requester_half(payload, public_key_requester, public_key_responder, signature_requester):
    return pack(requester_half_format, *(public_key_requester, public_key_responder,
                                         payload.up, payload.down,
                                         payload.total_up_requester, payload.total_down_requester,
                                         payload.sequence_number_requester, payload.previous_hash_requester,
                                         signature_requester))


def encode_block_crawl(payload):
    """
    This function encodes a block for the crawler.
    :param payload: Payload containing the data as properties, including the requester and responder,
    for example a crawl response payload.
    :return: encoding
    """
    return pack(crawl_response_format, *(payload.up, payload.down,
                                         payload.total_up_requester, payload.total_down_requester,
                                         payload.sequence_number_requester, payload.previous_hash_requester,
                                         payload.total_up_responder, payload.total_down_responder,
                                         payload.sequence_number_responder, payload.previous_hash_responder,
                                         payload.public_key_requester, payload.signature_requester,
                                         payload.public_key_responder, payload.signature_responder))
