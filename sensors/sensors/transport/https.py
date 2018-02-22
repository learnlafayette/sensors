from datetime import datetime, timedelta

import requests
from requests_toolbelt.adapters import host_header_ssl
from requests.exceptions import ConnectionError

from sensors.common import logging
from sensors.domain.transport import Transport
from sensors.config.constants import *
from sensors.config import get_config_element
from sensors.transport import *
from sensors.persistence.sqlite import SqliteRepository


class HttpsTransport(Transport):
    """HTTPS transport with JWT authentication

    """
    DEFAULT_JWT_TTL = "15"
    DEFAULT_TRANSMIT_INTERVAL_SECONDS = "15"
    DEFAULT_VERIFY_SSL = "true"

    SUCCESS_STATUS_CODE = 201
    ERROR_RESPONSE = 'error'

    # JWT authentication request token
    AUTH_TEMPLATE = '''{{"id":"{id}","key":"{key}"}}'''

    def __init__(self, typ, **kwargs):
        # Make sure required elements are present
        get_config_element(CFG_TRANSPORT_HTTPS_AUTH_URL,
                           kwargs, CFG_PROPERTIES)
        get_config_element(CFG_URL,
                           kwargs, CFG_PROPERTIES)
        get_config_element(CFG_TRANSPORT_HTTPS_JWT_ID,
                           kwargs, CFG_PROPERTIES)
        get_config_element(CFG_TRANSPORT_HTTPS_JWT_KEY,
                           kwargs, CFG_PROPERTIES)
        super().__init__(typ, **kwargs)

        self.jwt_token = (None, None)
        self.session = requests.session()
        if not self.verify_ssl():
            self.session.mount('https://', host_header_ssl.HostHeaderSSLAdapter())
        self.auth_ttl = self.jwt_token_ttl_minutes()

        self.logger = logging.get_instance()

    def transmit(self, repo: SqliteRepository):
        obs = repo.get_observations()
        self.logger.debug("Transmitter: read {0} observations from DB.".format(len(obs)))
        if len(obs) > 0:
            # Serialize observations to SensorThings dataArray JSON
            obs_dict = observations_list_to_dict(obs)
            json = observations_to_json(obs_dict)
            self.logger.debug("Transmitter: JSON payload: {0}".format(json))
            # POST observations
            self._jwt_authenticate()

            headers = {'Content-Type': 'application/json',
                       'Authorization': "Bearer {token}".format(token=self.jwt_token[0])}
            self.logger.debug("Transmitter: Posting data to {0}...".format(self.url()))
            try:
                r = self.session.post(self.url(), headers=headers, data=json, verify=self.verify_ssl())
            except ConnectionError as e:
                raise TransmissionException("POST failed due to error: {0}".format(str(e)))
            self.logger.debug("Transmitter: Status code was {0}".format(r.status_code))
            if r.status_code != self.SUCCESS_STATUS_CODE:
                raise TransmissionException("Transmission failed with status code: {0}".format(r.status_code))

            # Remove observations from local data, unless the observation could not be
            #   created, then update its status to error.
            ids_to_delete = []
            ids_to_update_status = []

            for (i, e) in enumerate(r.json()):
                if e == self.ERROR_RESPONSE:
                    ids_to_update_status.append(obs[i].id)
                else:
                    ids_to_delete.append(obs[i].id)

            repo.delete_observations(ids_to_delete)
            self.logger.debug("Transmitter: Successfully submitted {0} observations.".format(len(ids_to_delete)))
            repo.update_observation_status(ids_to_update_status, status=SqliteRepository.STATUS_ERROR)
            mesg = ("Transmitter: Failed to submit {0} observations, "
                    "which were retained in local database with status {1}.").format(len(ids_to_update_status),
                                                                                     SqliteRepository.STATUS_ERROR)
            self.logger.debug(mesg)

    def _jwt_authenticate(self):
        new_token = self.jwt_token
        auth_required = False

        # Figure out if authentication is required, that is: (1) if we have never authenticated (token_timestamp is None);
        #   or (2) token_timestamp is later than or equal to the current time + self.auth_ttl
        token_timestamp = self.jwt_token[1]
        if token_timestamp is None:
            self.logger.debug("Transmitter: Auth token is null, authenticating ...")
            auth_required = True
        else:
            token_expired_after = token_timestamp + self.auth_ttl
            if datetime.utcnow() >= token_expired_after:
                self.logger.debug("Transmitter: Auth token expired, re-authenticating ...")
                auth_required = True

        if auth_required:
            json = self.AUTH_TEMPLATE.format(id=self.jwt_id(), key=self.jwt_key())
            headers = {'Content-Type': 'application/json'}
            url = self.auth_url()
            try:
                r = self.session.post(url, headers=headers, data=json, verify=self.verify_ssl())
            except ConnectionError as e:
                raise AuthenticationException(
                    "Unable to authenticate to {0} due to error: {1}".format(url, str(e)))
            self.logger.debug(("Transmitter: Auth status code was {0}".format(r.status_code)))
            if r.status_code != 200:
                raise AuthenticationException("Authentication failed with status code {0}".format(str(r.status_code)))
            else:
                new_token = (r.json()["token"], datetime.datetime.utcnow())
            self.jwt_token = new_token

    def identifier(self) -> str:
        return Transport.IDENTIFIER_SEPARATOR.join((self.typ, self.properties[CFG_URL]))

    def auth_url(self) -> str:
        return self.properties[CFG_TRANSPORT_HTTPS_AUTH_URL]

    def url(self) -> str:
        return self.properties[CFG_URL]

    def jwt_id(self) -> str:
        return self.properties[CFG_TRANSPORT_HTTPS_JWT_ID]

    def jwt_key(self) -> str:
        return self.properties[CFG_TRANSPORT_HTTPS_JWT_KEY]

    def verify_ssl(self) -> bool:
        return bool(self.properties.get(CFG_TRANSPORT_HTTPS_VERIFY_SSL,
                                        self.DEFAULT_VERIFY_SSL))

    def jwt_token_ttl_minutes(self) -> timedelta:
        return timedelta(minutes=int(self.properties.get(CFG_TRANSPORT_HTTPS_JWT_TTL, self.DEFAULT_JWT_TTL)))

