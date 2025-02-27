/*************************************
* Initialization
**************************************/
window.addEventListener('load', cleanUploadsInProgress)

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
async function cleanUploadsInProgress() {
    setStatus('checking for uploads in progress');
    // Get uploads in progress
    const url = `/api/stac/v0.9/collections/${window.collection_name}/items/${window.item_name}/assets/${window.asset_name}/uploads?status=in-progress`;
    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Response status: ${response.status} ${response.statusText}`);
        }

        const json = await response.json();
        if (json.uploads.length == 0) {
            setStatus('ready to upload');
            return
        }
        for (const u of json.uploads) {
            abortMultipartUpload(u.upload_id);
        }
    } catch (error) {
        console.log(error);
        setError(`GetUploadsInProgress: ${error.responseText}`);
    }
}

// Abort the upload by upload_id
async function abortMultipartUpload(upload_id) {
    setStatus('aborting upload in progress');
    const url = `/api/stac/v0.9/collections/${window.collection_name}/items/${window.item_name}/assets/${window.asset_name}/uploads/${upload_id}/abort`;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': window.csrf_token,
            },
        });
        if (!response.ok) {
            throw new Error(`Response status: ${response.status} ${response.statusText}`);
        }

        setStatus('ready to upload');
    } catch (error) {
        console.log(error);
        setError(`AbortUploadsInProgress: ${error.responseText}`);
    }
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
    const reader = new FileReader();
    reader.onload = function (event) {
        const binary = event.target.result;

        // Create md5 hash, base64 encoded
        const md5 = CryptoJS.MD5(binary).toString(CryptoJS.enc.Base64);
        // Create multihash and call to create presigned url
        hashValue(binary)
            .then(multihash => createPresigned(md5, multihash, binary))
    };
    reader.readAsText(file);
}

// Create a new asset upload to get a presigned url.
// On success calls `uploadFile`.
async function createPresigned(md5, multi, file) {
    setStatus(`Creating presigned url...`);
    const url = `/api/stac/v0.9/collections/${window.collection_name}/items/${window.item_name}/assets/${window.asset_name}/uploads`;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': window.csrf_token,
                'Content-Type': 'application/json; charset=utf-8',
            },
            body: JSON.stringify({
                'number_parts': 1,
                'md5_parts': [
                    {
                        'part_number': 1,
                        'md5': md5,
                    }
                ],
                'file:checksum': multi,
            }),
        });
        if (!response.ok) {
            throw new Error(`Response status: ${response.status} ${response.statusText}`);
        }

        const json = await response.json();
        uploadFile(json, file)
    } catch (error) {
        console.log(error);
        setError(`CreatePreSignedURL: ${error}`);
    }
}

// Upload file to s3 using the presigned url.
// On success calls `completeMultipartUpload`
async function uploadFile(data, file) {
    setStatus(`Uploading file to s3...`);
    const url = data.urls[0].url;
    try {
        const response = await fetch(url, {
            method: 'PUT',
            headers: {
                'Content-MD5': data.md5_parts[0].md5,
                'Content-Type': 'binary/octet-stream',
            },
            body: file,
        });
        if (!response.ok) {
            throw new Error(`Response status: ${response.status} ${response.statusText}`);
        }

        let etag = response.headers.get('ETag');
        completeMultipartUpload(data, etag)
    } catch (error) {
        console.log(error);
        setError(`UploadFileToS3: ${error}`);
        abortMultipartUpload(data.upload_id);
    }
}

// Complete the asset upload.
// On success redirects back to asset overview.
async function completeMultipartUpload(data, etag) {
    setStatus(`Completing upload...`);
    const url = `/api/stac/v0.9/collections/${window.collection_name}/items/${window.item_name}/assets/${window.asset_name}/uploads/${data.upload_id}/complete`;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': window.csrf_token,
                'Content-Type': 'application/json; charset=utf-8',
            },
            body: JSON.stringify({
                'parts': [
                    {
                        'part_number': 1,
                        'etag': etag,
                    }
                ],
            }),
        });
        if (!response.ok) {
            throw new Error(`Response status: ${response.status} ${response.statusText}`);
        }

        // Remove end of url path '/api/stac/admin/stac_api/asset/3/change/upload/'
        // and redirect back to asset details.
        let path = window.location.pathname.split('/');
        let strippedPath = path.slice(0, path.length - 2).join('/');
        window.location.href = strippedPath
    } catch (error) {
        console.log(error);
        setError(`CompleteUpload: ${error.responseText}`);
        abortMultipartUpload(data.upload_id);
    }
}
