"""Embed GPS data into image EXIF."""

from PIL import Image
import piexif


class GPSEmbedder:
    """Embed GPS data into image EXIF."""

    @staticmethod
    def decimal_to_dms(decimal):
        """Convert decimal degrees to degrees, minutes, seconds."""
        decimal = abs(decimal)
        degrees = int(decimal)
        minutes_decimal = (decimal - degrees) * 60
        minutes = int(minutes_decimal)
        seconds = (minutes_decimal - minutes) * 60
        return ((degrees, 1), (minutes, 1), (int(seconds * 100), 100))

    @staticmethod
    def embed_gps(image_path, gps_data):
        """Embed GPS data into image EXIF.

        Args:
            image_path: Path to the image file.
            gps_data: Dict with 'latitude', 'longitude', and optional 'altitude'.

        Returns:
            True on success, False on failure.
        """
        try:
            img = Image.open(image_path)

            try:
                exif_dict = piexif.load(image_path)
            except Exception:
                exif_dict = {
                    "0th": {},
                    "Exif": {},
                    "GPS": {},
                    "1st": {},
                    "thumbnail": None,
                }

            gps_ifd = {}

            lat = gps_data["latitude"]
            lon = gps_data["longitude"]

            gps_ifd[piexif.GPSIFD.GPSLatitude] = GPSEmbedder.decimal_to_dms(abs(lat))
            gps_ifd[piexif.GPSIFD.GPSLatitudeRef] = b"N" if lat >= 0 else b"S"

            gps_ifd[piexif.GPSIFD.GPSLongitude] = GPSEmbedder.decimal_to_dms(abs(lon))
            gps_ifd[piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"

            if gps_data["altitude"] is not None:
                alt = abs(gps_data["altitude"])
                gps_ifd[piexif.GPSIFD.GPSAltitude] = (int(alt * 100), 100)
                gps_ifd[piexif.GPSIFD.GPSAltitudeRef] = (
                    0 if gps_data["altitude"] >= 0 else 1
                )

            exif_dict["GPS"] = gps_ifd

            exif_bytes = piexif.dump(exif_dict)
            img.save(image_path, exif=exif_bytes, quality=95)

            return True
        except Exception as e:
            print(f"Error embedding GPS in {image_path}: {e}")
            return False
