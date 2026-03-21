"""Parse DJI SRT files to extract GPS and metadata."""

import re


class SRTParser:
    """Parse DJI SRT files to extract GPS and metadata."""

    @staticmethod
    def parse_srt(srt_path):
        """Parse SRT file and return list of frames with metadata."""
        frames = []

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        blocks = re.split(r"\n\n+", content.strip())

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            timestamp_line = lines[1]
            match = re.search(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", timestamp_line)
            if not match:
                continue

            hours, minutes, seconds, ms = map(int, match.groups())
            timestamp_sec = hours * 3600 + minutes * 60 + seconds + ms / 1000.0

            metadata_text = " ".join(lines[2:])

            frame_data = {
                "timestamp": timestamp_sec,
                "latitude": None,
                "longitude": None,
                "altitude": None,
                "raw": metadata_text,
            }

            # Try GPS:(lon, lat) format
            gps_match = re.search(
                r"GPS:\s*\(([-\d.]+)\s*,\s*([-\d.]+)\)", metadata_text
            )
            if gps_match:
                frame_data["longitude"] = float(gps_match.group(1))
                frame_data["latitude"] = float(gps_match.group(2))

            # Fallback: [latitude: ...] [longtitude: ...] format
            if frame_data["latitude"] is None:
                lat_match = re.search(
                    r"\[latitude:\s*([-\d.]+)\]", metadata_text, re.IGNORECASE
                )
                lon_match = re.search(
                    r"\[longtitude:\s*([-\d.]+)\]", metadata_text, re.IGNORECASE
                )
                if lat_match:
                    frame_data["latitude"] = float(lat_match.group(1))
                if lon_match:
                    frame_data["longitude"] = float(lon_match.group(1))

            # Altitude
            alt_match = re.search(r"H:\s*([-\d.]+)m", metadata_text)
            if alt_match:
                frame_data["altitude"] = float(alt_match.group(1))
            elif frame_data["altitude"] is None:
                alt_match = re.search(
                    r"\[altitude:\s*([-\d.]+)\]", metadata_text, re.IGNORECASE
                )
                if alt_match:
                    frame_data["altitude"] = float(alt_match.group(1))

            frames.append(frame_data)

        return frames

    @staticmethod
    def get_gps_for_timestamp(frames_data, timestamp):
        """Get GPS data for a specific timestamp (closest match)."""
        if not frames_data:
            return None

        closest = min(frames_data, key=lambda x: abs(x["timestamp"] - timestamp))

        if closest["latitude"] is None or closest["longitude"] is None:
            return None

        return {
            "latitude": closest["latitude"],
            "longitude": closest["longitude"],
            "altitude": closest["altitude"],
        }
