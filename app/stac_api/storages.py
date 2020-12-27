from storages.backends.s3boto3 import S3Boto3Storage


class S3Storage(S3Boto3Storage):
    # pylint: disable=abstract-method
    # pylint: disable=no-member

    def get_object_parameters(self, name):
        """
        Returns a dictionary that is passed to file upload. Override this
        method to adjust this on a per-object basis to set e.g ContentDisposition.

        Args:
            name: string
                file name

        Returns:
            Parameters from AWS_S3_OBJECT_PARAMETERS plus the file sha256 checksum as MetaData
        """
        params = self.object_parameters.copy()
        if 'Metadata' not in params:
            params['Metadata'] = {}

        params['Metadata']['sha256'] = getattr(self, '_tmp_sha256', None)
        return params
