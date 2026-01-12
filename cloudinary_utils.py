from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api
from config import Config
import os

# Configure Cloudinary
cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET,
    secure=True
)

def upload_to_cloudinary(file, folder="products"):
    """
    Upload file to Cloudinary
    
    Args:
        file: File object from request.files
        folder: Folder path in Cloudinary
    
    Returns:
        dict: {'url': image_url, 'public_id': public_id}
    """
    try:
        # Validate file
        if not file or not file.filename:
            return None
        
        # Secure the filename
        filename = secure_filename(file.filename)
        
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file,
            folder=f"thriveos/{folder}",
            public_id=os.path.splitext(filename)[0],
            overwrite=True,
            resource_type="auto"
        )
        
        return {
            'url': upload_result['secure_url'],
            'public_id': upload_result['public_id']
        }
        
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        return None

def delete_from_cloudinary(public_id):
    """
    Delete image from Cloudinary
    
    Args:
        public_id: Cloudinary public ID
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if public_id:
            result = cloudinary.uploader.destroy(public_id)
            return result.get('result') == 'ok'
        return False
    except Exception as e:
        print(f"Cloudinary delete error: {e}")
        return False

def optimize_image_url(url, transformations=None):
    """
    Apply Cloudinary transformations to optimize image
    
    Args:
        url: Original Cloudinary URL
        transformations: List of transformation strings
    
    Returns:
        str: Optimized image URL
    """
    if not url or 'cloudinary.com' not in url:
        return url
    
    if not transformations:
        # Default transformations for product images
        transformations = [
            "c_fill",
            "w_800",
            "h_800",
            "q_auto:good",
            "f_auto"
        ]
    
    # Split URL to insert transformations
    parts = url.split('/upload/')
    if len(parts) == 2:
        return f"{parts[0]}/upload/{','.join(transformations)}/{parts[1]}"
    
    return url

def get_image_thumbnail(url, width=200, height=200):
    """
    Get thumbnail URL for product listings
    
    Args:
        url: Original Cloudinary URL
        width: Thumbnail width
        height: Thumbnail height
    
    Returns:
        str: Thumbnail URL
    """
    if not url or 'cloudinary.com' not in url:
        return url
    
    transformations = [
        "c_fill",
        f"w_{width}",
        f"h_{height}",
        "q_auto:good"
    ]
    
    return optimize_image_url(url, transformations)