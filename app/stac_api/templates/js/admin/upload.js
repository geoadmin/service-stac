/*************************************
* Initialization
**************************************/
window.onload = function () {
    current_status_span = document.getElementById('current_status')
    cleanUploadsInProgress()
}

/*************************************
* Helper functions
**************************************/
function setStatus(text) {
    document.getElementById('current_status').textContent = text;
}
function setError(text) {
    document.getElementById('error_box').style.display = 'block';
    document.getElementById('error').textContent = text;
}
function hashValue(val) {
    return crypto.subtle
        .digest('SHA-256', new TextEncoder('utf-8').encode(val))
        .then(h => {
            const prefix = '1220'; // for sha2-256 according to https://multiformats.io/multihash/
            let hexes = [],
                view = new DataView(h);
            for (let i = 0; i < view.byteLength; i += 4)
                hexes.push(('00000000' + view.getUint32(i).toString(16)).slice(-8));
            return prefix + hexes.join('');
        });
}

/*************************************
* Functions to upload files
**************************************/

// Check for any uploads in progress and abort them.
function cleanUploadsInProgress() {
    setStatus('checking for uploads in progress');
    // Get uploads in progress
    $.ajax({
        type: 'GET',
        url: `/api/stac/v1/collections/${collection_name}/items/${item_name}/assets/${asset_name}/uploads?status=in-progress`,
        success: function (data) {
            if (data.uploads.length == 0) {
                setStatus('ready to upload');
                return
            }
            for (u of data.uploads) {
                abortMultipartUpload(u.upload_id);
            }
        },
        error: function (error) {
            console.log(error);
            setError(`GetUploadsInProgress: ${error.responseText}`);
        }
    })
}

// Abort the upload by upload_id
function abortMultipartUpload(upload_id) {
    setStatus('aborting upload in progress');
    $.ajax({
        type: 'POST',
        url: `/api/stac/v1/collections/${collection_name}/items/${item_name}/assets/${asset_name}/uploads/${upload_id}/abort`,
        headers: {
            'X-CSRFToken': csrf_token,
        },
        success: function (data) {
            setStatus('ready to upload');
        },
        error: function (error) {
            console.log(error);
            setError(`AbortUploadsInProgress: ${error.responseText}`);
        }
    })
}

// Start the upload process.
// Reads file, creates md5 and multihash.
// Calls `createPresigned`.
function handleFileFormSubmit() {
    const fileInput = document.getElementById('id_file');
    if (fileInput.files.length == 0) {
        setError('no file selected')
        return
    }
    const file = fileInput.files[0]; /* now you can work with the file */
    var reader = new FileReader();
    reader.onload = function (event) {
        var binary = event.target.result;

        // Create md5 hash, base64 encoded
        var md5 = CryptoJS.MD5(binary).toString(CryptoJS.enc.Base64);
        // Create multihash and call to create presigned url
        var multi = hashValue(binary)
            .then(multihash => createPresigned(md5, multihash, binary))
    };
    reader.readAsBinaryString(file);
}

// Create a new asset upload to get a presigned url.
// On success calls `uploadFile`.
function createPresigned(md5, multi, file) {
    setStatus(`Creating presigned url...`);
    $.ajax({
        type: 'POST',
        url: `/api/stac/v1/collections/${collection_name}/items/${item_name}/assets/${asset_name}/uploads`,
        headers: {
            'X-CSRFToken': csrf_token,
        },
        contentType: 'application/json; charset=utf-8',
        data: JSON.stringify({
            'number_parts': 1,
            'md5_parts': [
                {
                    'part_number': 1,
                    'md5': md5,
                }
            ],
            'file:checksum': multi,
        }),
        xhrFields: {
            withCredentials: true
        },
        success: function (data) {
            uploadFile(data, file)
        },
        error: function (error) {
            console.log(error);
            setError(`CreatePreSignedURL: ${error.responseText}`);
        }
    })
}

// Upload file to s3 using the presigned url.
// On success calls `completeMultipartUpload`
function uploadFile(data, file) {
    setStatus(`Uploading file to s3...`);
    $.ajax({
        type: 'PUT',
        url: data.urls[0].url,
        headers: {
            'Content-MD5': data.md5_parts[0].md5,
        },
        contentType: 'binary/octet-stream',
        processData: false,
        data: file,
        success: function (s3data, textStatus, request) {
            let etag = request.getResponseHeader('ETag');
            completeMultipartUpload(data, etag)
        },
        error: function (error) {
            console.log(error);
            setError(`UploadFileToS3: ${error.responseText}`);
            abortMultipartUpload(data.upload_id);
        }
    })
}

// Complete the asset upload.
// On success redirects back to asset overview.
function completeMultipartUpload(data, etag) {
    setStatus(`Completing upload...`);
    $.ajax({
        type: 'POST',
        url: `/api/stac/v1/collections/${collection_name}/items/${item_name}/assets/${asset_name}/uploads/${data.upload_id}/complete`,
        headers: {
            'X-CSRFToken': csrf_token,
        },
        contentType: 'application/json; charset=utf-8',
        data: JSON.stringify({
            'parts': [
                {
                    'part_number': 1,
                    'etag': etag,
                }
            ],
        }),
        xhrFields: {
            withCredentials: true
        },
        success: function (data) {
            // Remove end of url path '/api/stac/admin/stac_api/asset/3/change/upload/'
            // and redirect back to asset details.
            var path = window.location.pathname.split('/');
            var strippedPath = path.slice(0, path.length - 2).join('/');
            window.location.href = strippedPath
        },
        error: function (error) {
            console.log(error);
            setError(`CompleteUpload: ${error.responseText}`);
        }
    })
}
