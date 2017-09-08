#! /usr/bin/env python3
import argparse
import json
import logging
import logging.config
import os
import sys
import time
from datetime import datetime, timedelta
from concurrent import futures

# Add Generated folder to module path.
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(PARENT_DIR, 'Generated'))

import ServerSideExtension_pb2 as SSE
import grpc
from SSEData import FunctionType
from ScriptEval import ScriptEval

import platform
import configparser
import csv
from cryptography.fernet import Fernet

_ONE_DAY_IN_SECONDS = 60 * 60 * 24

config = configparser.ConfigParser()

config_path = os.path.join(os.sep, 'configs', 'qpi.config')
config.read(config_path)

configAudit = config['Audit']
auditLogPath = configAudit.get('auditLogPath','logs')

configCrypto = config['Cryptography']

cipher_key = str.encode(configCrypto['key'])
cipher = Fernet(cipher_key)

configgetField = config['getField']
dataLastUpdated = None
qpiData = None
qpiObsfData = None
qpiAccess = None

#Number test...
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        pass

    return False



#This function will update (if needed) the data for the getField() function.
def dataUpdate():
    dataPath = configgetField.get('dataPath','/data/data.json')
    obfuscatedPath = configgetField.get('obfuscatedPath','/data/data.json')
    accessPath = configgetField.get('accessPath','/data/data.json')
    dataReloadFrequency = configgetField.get('reloadFrequency','L').upper()

    #Not optimal but will need to fix later.
    global qpiData
    global qpiObfuscated
    global qpiAccess
    global dataLastUpdated

    if dataLastUpdated is None:
        shouldReloadTime = datetime.now() - timedelta(seconds = 60*60)
    elif dataReloadFrequency == 'H':
        shouldReloadTime = dataLastUpdated + timedelta(seconds = 60*60)
    elif dataReloadFrequency == 'D':
        shouldReloadTime = dataLastUpdated + timedelta(seconds = 60*60*24)
    elif is_number(dataReloadFrequency):
        shouldReloadTime = dataLastUpdated + timedelta(seconds = 60*dataReloadFrequency)
    else:
        #Don't update
        shouldReloadTime = datetime.now() + timedelta(seconds = 60*60)

    if datetime.now() >= shouldReloadTime:
        logging.info('Updating data files.')
        with open(dataPath) as jsonData:
            jsData = json.load(jsonData)
            qpiData = jsData["data"]

        if obfuscatedPath == dataPath:
            qpiObfuscated = jsData["obfuscated"]
        else:
            with open(obfuscatedPath) as jsonData:
                qpiObfuscated = json.load(jsonData)["obfuscated"]

        if accessPath == obfuscatedPath:
            qpiAccess = jsData["access"]
        else:
            with open(accessPath) as jsonData:
                qpiAccess = json.load(jsonData)["access"]

        dataLastUpdated = datetime.now()
        logging.info('Update complete.')


#This function will create a new audit file based on the auditTSPattern specified in the configuration file.
def csvlogger(rows):
    #Add the audit file prefix to the log path
    auditFile =  os.path.join(auditLogPath , configAudit.get('fileNamePrefix','QPI_Audit'))

    #Add server name to output file.
    auditFile = auditFile + '__' + platform.node() + '__'

    #Get TimeStamp pattern, format it, and add to AuditFile
    auditTSPattern = '%' + '_%'.join(configAudit.get('fileNameTSPattern','YmdH'))
    auditFile = auditFile + datetime.now().strftime(auditTSPattern) + '.csv'

    logging.debug("Audit Log File path: " + auditFile)

    #If the audit file already exists, remove header row...
    if os.path.isfile(auditFile):
        rows.pop(0)

    csvfile = open(auditFile, 'a')
    filewriter = csv.writer(csvfile, delimiter=configAudit.get('delimiter',','), lineterminator='\n', quotechar=configAudit.get('quotechar',"'"), quoting=csv.QUOTE_MINIMAL)
    filewriter.writerows(rows)
    csvfile.close()


class ExtensionService(SSE.ConnectorServicer):
    """
    A Qlik Privacy Encryption Sample SSE-plugin created from the HelloWorld example.
    """

    def __init__(self, funcdef_file):
        """
        Class initializer.
        :param funcdef_file: a function definition JSON file
        """
        self._function_definitions = funcdef_file
        self.ScriptEval = ScriptEval()

        if not os.path.exists('logs'):
            os.mkdir('logs')

        log_file = os.path.join(os.sep, 'configs', 'logger.config')
        logging.config.fileConfig(log_file)
        logging.info('Logging enabled')

        if not os.path.exists(auditLogPath):
            os.mkdir(auditLogPath)

        logging.info("Audit log path: " + auditLogPath)
        logging.info("Config path: " + config_path)

        dataUpdate()


    @property
    def function_definitions(self):
        """
        :return: json file with function definitions
        """
        return self._function_definitions

    @property
    def functions(self):
        """
        :return: Mapping of function id and implementation
        """
        return {
            0: '_decrypt',
            1: '_encrypt',
            2: '_getField',
            3: '_cache',
            4: '_no_cache'
        }

    @staticmethod
    def _get_function_id(context):
        """
        Retrieve function id from header.
        :param context: context
        :return: function id
        """
        metadata = dict(context.invocation_metadata())
        header = SSE.FunctionRequestHeader()
        header.ParseFromString(metadata['qlik-functionrequestheader-bin'])

        return header.functionId

    """
    Implementation of added functions.
    """

    @staticmethod
    def _decrypt(request, context):
        """
        Mirrors the input and sends back the same data.
        :param request: iterable sequence of bundled rows
        :return: the same iterable sequence as received
        """
        mytime = datetime.utcnow()
        params = []

        csvrows = []
        csvrows.append(['DateTimeUTC','FieldRef','UserRef','Comment'])

        logging.debug("Request: " + str(request) + "\n")


        for request_rows in request:
            logging.debug("Request rows: " + str(request_rows) + "\n")
            response_rows = []

            for row in request_rows.rows:

                # Retrieve string value of parameter and append to the params variable
                params = [d.strData for d in row.duals]

                #Decrypt the first parameter here...
                try:
                    decryptedValue = str(cipher.decrypt(str.encode([d.strData for d in row.duals][0])),'utf-8')

                except:
                    decryptedValue = 'Can not decrypt data, see log file.'
                    logging.error('Error in decryption occurred:\n     Either the string provided is not encrypted or the Cipher token in qpi.config does not match token used to originally encrypt the data.\n     To fix the token, either update qpi.config with the correct key OR re-encrypt the data with a new key.')

                # Create an iterable of dual with the result
                duals = iter([SSE.Dual(strData=decryptedValue)])

                response_rows.append(SSE.Row(duals=duals))

                csvrows.append([mytime,params[1],params[2],params[3]])

            #Added threading from https://stackoverflow.com/questions/39440015/how-to-do-simple-async-calls-in-python
            #    needs to be thoroughly tested on LARGE data volumes
            with futures.ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(csvlogger,csvrows)


        yield SSE.BundledRows(rows=response_rows)


    @staticmethod
    def _encrypt(request, context):
        """
        Mirrors the input and sends back the same data.
        :param request: iterable sequence of bundled rows
        :return: the same iterable sequence as received
        """
        for request_rows in request:
            # Iterate over rows
            for row in request_rows.rows:
                #Encrypt the first parameter here...
                encryptedValue = cipher.encrypt(str.encode([d.strData for d in row.duals][0]))

                # Create an iterable of dual with the result
                duals = iter([SSE.Dual(strData=encryptedValue)])

        yield SSE.BundledRows(rows=[SSE.Row(duals=duals)])

    @staticmethod
    def _getField(request, context):
        """
        Mirrors the input and sends back the same data.
        :param request: iterable sequence of bundled rows
        :return: the same iterable sequence as received
        """
        mytime = datetime.utcnow()
        params = []

        csvrows = []
        csvrows.append(['DateTimeUTC','FieldRef','UserRef','Comment'])

        logging.debug("Request: " + str(request) + "\n")

        dataUpdate()

        #Not optimal but will need to fix later.
        global qpiData
        global qpiObsfData
        global qpiAccess

        for request_rows in request:
            logging.debug("Request rows: " + str(request_rows) + "\n")
            response_rows = []

            for row in request_rows.rows:

                # Retrieve string value of parameter and append to the params variable
                params = [d.strData for d in row.duals]

                #Retrieve the requested value from the loaded data here...
                try:
                    if params[2] in qpiAccess:
                        returnValue = str(qpiData[params[1]][params[0]])

                        csvrows.append([mytime,params[1],params[2],'Field: ' + params[0] + ' - ' + params[3]])

                        #Added threading from https://stackoverflow.com/questions/39440015/how-to-do-simple-async-calls-in-python
                        #    needs to be thoroughly tested on LARGE data volumes
                        with futures.ThreadPoolExecutor(max_workers=1) as executor:
                            executor.submit(csvlogger,csvrows)
                    else:
                        # User is not allowed to see real data, returning obfuscated data and no need to log access.
                        returnValue = str(qpiObfuscated[params[1]][params[0]])

                except:
                    returnValue = 'Can not retrieve requested data, see log file.'#
                    logging.error('Error in retrieving data\nNo data exists for ID: ' + params[1] + ' Field: ' + params[0] + ' for User: ' + params[2] + ' Comment: ' + params[3])

                # Create an iterable of dual with the result
                duals = iter([SSE.Dual(strData=returnValue)])

                response_rows.append(SSE.Row(duals=duals))


        yield SSE.BundledRows(rows=response_rows)

    @staticmethod
    def _cache(request, context):
        """
        Cache enabled. Add the datetime stamp to the end of each string value.
        :param request: iterable sequence of bundled rows
        :param context: not used.
        :return: string
        """
        # Iterate over bundled rows
        for request_rows in request:
            # Iterate over rows
            for row in request_rows.rows:
                # Retrieve string value of parameter and append to the params variable
                # Length of param is 1 since one column is received, the [0] collects the first value in the list
                param = [d.strData for d in row.duals][0]

                # Join with current timedate stamp
                result = param + ' ' + datetime.now().isoformat()
                # Create an iterable of dual with the result
                duals = iter([SSE.Dual(strData=result)])

                # Yield the row data as bundled rows
                yield SSE.BundledRows(rows=[SSE.Row(duals=duals)])

    @staticmethod
    def _no_cache(request, context):
        """
        Cache disabled. Add the datetime stamp to the end of each string value.
        :param request:
        :param context: used for disabling the cache in the header.
        :return: string
        """
        # Disable caching.
        md = (('qlik-cache', 'no-store'),)
        context.send_initial_metadata(md)

        # Iterate over bundled rows
        for request_rows in request:
            # Iterate over rows
            for row in request_rows.rows:
                # Retrieve string value of parameter and append to the params variable
                # Length of param is 1 since one column is received, the [0] collects the first value in the list
                param = [d.strData for d in row.duals][0]

                # Join with current timedate stamp
                result = param + ' ' + datetime.now().isoformat()
                # Create an iterable of dual with the result
                duals = iter([SSE.Dual(strData=result)])

                # Yield the row data as bundled rows
                yield SSE.BundledRows(rows=[SSE.Row(duals=duals)])


    """
    Implementation of rpc functions.
    """

    def GetCapabilities(self, request, context):
        """
        Get capabilities.
        Note that either request or context is used in the implementation of this method, but still added as
        parameters. The reason is that gRPC always sends both when making a function call and therefore we must include
        them to avoid error messages regarding too many parameters provided from the client.
        :param request: the request, not used in this method.
        :param context: the context, not used in this method.
        :return: the capabilities.
        """
        logging.info('GetCapabilities')
        # Create an instance of the Capabilities grpc message
        # Enable(or disable) script evaluation
        # Set values for pluginIdentifier and pluginVersion
        capabilities = SSE.Capabilities(allowScript=False,
                                        pluginIdentifier='Qlik Privacy Integration',
                                        pluginVersion='v1.0.0-beta1')

        # If user defined functions supported, add the definitions to the message
        with open(self.function_definitions) as json_file:
            # Iterate over each function definition and add data to the capabilities grpc message
            for definition in json.load(json_file)['Functions']:
                function = capabilities.functions.add()
                function.name = definition['Name']
                function.functionId = definition['Id']
                function.functionType = definition['Type']
                function.returnType = definition['ReturnType']

                # Retrieve name and type of each parameter
                for param_name, param_type in sorted(definition['Params'].items()):
                    function.params.add(name=param_name, dataType=param_type)

                logging.info('Adding to capabilities: {}({})'.format(function.name,
                                                                     [p.name for p in function.params]))

        return capabilities

    def ExecuteFunction(self, request_iterator, context):
        """
        Execute function call.
        :param request_iterator: an iterable sequence of Row.
        :param context: the context.
        :return: an iterable sequence of Row.
        """
        # Retrieve function id
        func_id = self._get_function_id(context)

        # Call corresponding function
        logging.info('ExecuteFunction (functionId: {})'.format(func_id))

        return getattr(self, self.functions[func_id])(request_iterator, context)

    def EvaluateScript(self, request, context):
        """
        This plugin provides functionality only for script calls with no parameters and tensor script calls.
        :param request:
        :param context:
        :return:
        """
        # Parse header for script request
        metadata = dict(context.invocation_metadata())
        header = SSE.ScriptRequestHeader()
        header.ParseFromString(metadata['qlik-scriptrequestheader-bin'])

        # Retrieve function type
        func_type = self.ScriptEval.get_func_type(header)

        # Verify function type
        if (func_type == FunctionType.Aggregation) or (func_type == FunctionType.Tensor):
            return self.ScriptEval.EvaluateScript(header, request, context, func_type)
        else:
            # This plugin does not support other function types than aggregation  and tensor.
            # Make sure the error handling, including logging, works as intended in the client
            msg = 'Function type {} is not supported in this plugin.'.format(func_type.name)
            context.set_code(grpc.StatusCode.UNIMPLEMENTED)
            context.set_details(msg)
            # Raise error on the plugin-side
            raise grpc.RpcError(grpc.StatusCode.UNIMPLEMENTED, msg)

    """
    Implementation of the Server connecting to gRPC.
    """

    def Serve(self, port, pem_dir):
        """
        Sets up the gRPC Server with insecure connection on port
        :param port: port to listen on.
        :param pem_dir: Directory including certificates
        :return: None
        """
        # Create gRPC server
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        SSE.add_ConnectorServicer_to_server(self, server)

        if pem_dir:
            # Secure connection
            with open(os.path.join(pem_dir, 'sse_server_key.pem'), 'rb') as f:
                private_key = f.read()
            with open(os.path.join(pem_dir, 'sse_server_cert.pem'), 'rb') as f:
                cert_chain = f.read()
            with open(os.path.join(pem_dir, 'root_cert.pem'), 'rb') as f:
                root_cert = f.read()
            credentials = grpc.ssl_server_credentials([(private_key, cert_chain)], root_cert, True)
            server.add_secure_port('[::]:{}'.format(port), credentials)
            logging.info('*** Running server in secure mode on port: {} ***'.format(port))
        else:
            # Insecure connection
            server.add_insecure_port('[::]:{}'.format(port))
            logging.info('*** Running server in insecure mode on port: {} ***'.format(port))

        # Start gRPC server
        server.start()
        try:
            while True:
                time.sleep(_ONE_DAY_IN_SECONDS)
        except KeyboardInterrupt:
            server.stop(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', nargs='?', default='50054')
    parser.add_argument('--pem_dir', nargs='?')
    parser.add_argument('--definition-file', nargs='?', default='FuncDefs_qpi.json')
    args = parser.parse_args()

    # need to locate the file when script is called from outside it's location dir.
    def_file = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), args.definition_file)

    calc = ExtensionService(def_file)
    calc.Serve(args.port, args.pem_dir)
