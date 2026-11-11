import { Alert, Box, Button, CircularProgress, Typography } from '@mui/material';
import React from 'react';

import { missingCameras, RobotCamera, RobotCapabilities } from '../../services';

/** web_video_server answers 200 and sends nothing for a topic that does not exist. */
const NO_FRAME_TIMEOUT_MS = 10000;

const STREAM_WIDTH = 480;
const STREAM_HEIGHT = 360;
const STREAM_QUALITY = 60;

/**
 * MJPEG url of `web_video_server`. The slashes of the topic are kept as they are
 * (`?topic=/bcr_bot_1/front_camera/image_raw`), which is the documented form.
 */
export const buildStreamUrl = (
  baseUrl: string,
  topic: string,
  size: { width?: number; height?: number; quality?: number } = {
    width: STREAM_WIDTH,
    height: STREAM_HEIGHT,
    quality: STREAM_QUALITY,
  },
): string => {
  const params = [`topic=${encodeURIComponent(topic).replace(/%2F/gi, '/')}`];
  if (size.width) params.push(`width=${size.width}`);
  if (size.height) params.push(`height=${size.height}`);
  if (size.quality) params.push(`quality=${size.quality}`);
  return `${baseUrl.replace(/\/+$/, '')}/stream?${params.join('&')}`;
};

export type CameraAvailability =
  /** capabilities were not fetched yet */
  | { kind: 'unknown' }
  /** the robot declares no camera */
  | { kind: 'no-camera' }
  /** declared, but nobody publishes it (not launched, or DDS is still discovering) */
  | { kind: 'declared-missing'; names: string[] }
  | { kind: 'available'; camera: RobotCamera };

export const cameraAvailability = (
  capabilities: RobotCapabilities | undefined,
  loaded: boolean,
): CameraAvailability => {
  if (!loaded) return { kind: 'unknown' };
  if (!capabilities) return { kind: 'no-camera' };
  if (capabilities.cameras.length > 0)
    return { kind: 'available', camera: capabilities.cameras[0] };
  const missing = missingCameras(capabilities);
  return missing.length > 0 ? { kind: 'declared-missing', names: missing } : { kind: 'no-camera' };
};

type StreamStatus = 'loading' | 'live' | 'error';

interface StreamProps {
  url: string;
  robotName: string;
}

/**
 * One `<img>` per MJPEG stream. The stream never ends by itself, so on unmount or url change the
 * connection is closed by emptying `src`.
 */
const Stream = ({ url, robotName, onRetry }: StreamProps & { onRetry: () => void }) => {
  const imgRef = React.useRef<HTMLImageElement>(null);
  const [status, setStatus] = React.useState<StreamStatus>('loading');

  // The <img> is always mounted (hidden until the first frame), so this effect always has the node
  // it must close. The parent gives every stream (url + retry) its own instance via `key`, so the
  // state starts at `loading` each time.
  React.useEffect(() => {
    const img = imgRef.current;
    const timer = setTimeout(() => {
      setStatus((prev) => (prev === 'loading' ? 'error' : prev));
    }, NO_FRAME_TIMEOUT_MS);
    return () => {
      clearTimeout(timer);
      if (img) img.src = '';
    };
  }, [url]);

  // Giving up also closes the connection (a stream on a topic nobody publishes stays open).
  React.useEffect(() => {
    if (status === 'error' && imgRef.current) imgRef.current.src = '';
  }, [status]);

  return (
    <Box sx={{ position: 'relative', width: '100%', height: '100%', minHeight: 0 }}>
      {status === 'error' && (
        <Alert
          severity="warning"
          role="alert"
          action={
            <Button color="inherit" size="small" onClick={onRetry}>
              Reintentar
            </Button>
          }
        >
          No llegan imágenes de la cámara de {robotName}.
        </Alert>
      )}
      {status === 'loading' && (
        <Box
          role="status"
          aria-label="cargando cámara"
          sx={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}
        >
          <CircularProgress size={28} />
        </Box>
      )}
      <Box
        component="img"
        ref={imgRef}
        src={url}
        alt={`Cámara de ${robotName}`}
        onLoad={() => setStatus('live')}
        onError={() => setStatus('error')}
        sx={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          display: status === 'live' ? 'block' : 'none',
        }}
      />
    </Box>
  );
};

/** A retry mounts a new `Stream`, so the browser opens a new connection. */
const StreamWithRetry = ({ url, robotName }: StreamProps) => {
  const [attempt, setAttempt] = React.useState(0);
  return (
    <Stream
      key={`${url}#${attempt}`}
      url={url}
      robotName={robotName}
      onRetry={() => setAttempt((n) => n + 1)}
    />
  );
};

export interface RobotCameraViewProps {
  robotName: string;
  capabilities: RobotCapabilities | undefined;
  /** `false` until the first answer of `/robots/capabilities`. */
  capabilitiesLoaded: boolean;
  webVideoUrl: string;
}

export const RobotCameraView = ({
  robotName,
  capabilities,
  capabilitiesLoaded,
  webVideoUrl,
}: RobotCameraViewProps) => {
  const availability = cameraAvailability(capabilities, capabilitiesLoaded);

  switch (availability.kind) {
    case 'unknown':
      return (
        <Typography variant="body2" color="text.secondary" role="status">
          Consultando las cámaras…
        </Typography>
      );
    case 'no-camera':
      return (
        <Typography variant="body2" color="text.secondary" role="status">
          {robotName} no tiene cámara.
        </Typography>
      );
    case 'declared-missing':
      return (
        <Alert severity="info" role="status">
          La cámara declarada ({availability.names.join(', ')}) no está publicando. Puede que el
          robot no se haya lanzado con ella.
        </Alert>
      );
    case 'available':
      return (
        <StreamWithRetry
          url={buildStreamUrl(webVideoUrl, availability.camera.topic)}
          robotName={robotName}
        />
      );
  }
};

export default RobotCameraView;
