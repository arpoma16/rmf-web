import {
  Fullscreen as FullscreenIcon,
  Layers as LayersIcon,
  ZoomIn as ZoomInIcon,
  ZoomOut as ZoomOutIcon,
} from '@mui/icons-material';
import {
  Box,
  Checkbox,
  FormControl,
  FormControlLabel,
  FormGroup,
  IconButton,
  MenuItem,
  TextField,
} from '@mui/material';
import { Level } from 'api-client';
import React from 'react';
import { ChangeEvent } from 'react';

import { AppEvents } from '../app-events';

// Square 44px buttons, stacked, with the secondary ink color of the theme (`palette.info`).
const mapButtonSx = {
  width: 44,
  height: 44,
  marginTop: 1,
  borderRadius: '8px',
  border: 1,
  borderColor: 'divider',
  backgroundColor: 'background.paper',
  color: 'info.main',
  '&:hover': { backgroundColor: 'background.default' },
};

interface LayersControllerProps {
  disabledLayers: Record<string, boolean>;
  onChange: (event: ChangeEvent<HTMLInputElement>, value: string) => void;
  levels: Level[];
  currentLevel: Level;
  handleFullView: () => void;
  handleZoomIn: () => void;
  handleZoomOut: () => void;
}

export const LayersController = ({
  disabledLayers,
  onChange,
  levels,
  currentLevel,
  handleFullView,
  handleZoomIn,
  handleZoomOut,
}: LayersControllerProps) => {
  const [isHovered, setIsHovered] = React.useState(false);

  return (
    <Box
      sx={{
        position: 'absolute',
        top: '60px',
        left: '4px',
        width: 'auto',
        height: 'auto',
        zIndex: '1',
      }}
    >
      <FormControl>
        <TextField
          select
          id="level-select"
          label="Levels"
          variant="outlined"
          fullWidth
          margin="none"
          value={currentLevel.name}
          size="small"
          sx={{ width: '80px' }}
          onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e, e.target.value as string)}
        >
          {levels.map((level, i) => (
            <MenuItem key={i} value={level.name}>
              {level.name}
            </MenuItem>
          ))}
        </TextField>
      </FormControl>
      <div>
        <IconButton
          size="small"
          onClick={handleFullView}
          data-testid="full-view"
          aria-label="fit view"
          sx={mapButtonSx}
        >
          <FullscreenIcon />
        </IconButton>
      </div>
      <div>
        <IconButton
          size="small"
          onClick={handleZoomIn}
          data-testid="zoom-in"
          aria-label="zoom in"
          sx={mapButtonSx}
        >
          <ZoomInIcon />
        </IconButton>
      </div>
      <div>
        <IconButton
          size="small"
          onClick={handleZoomOut}
          data-testid="zoom-out"
          aria-label="zoom out"
          sx={mapButtonSx}
        >
          <ZoomOutIcon />
        </IconButton>
      </div>
      <div onMouseEnter={() => setIsHovered(true)} onMouseLeave={() => setIsHovered(false)}>
        <IconButton size="small" data-testid="layers" aria-label="layers" sx={mapButtonSx}>
          <LayersIcon />
        </IconButton>
        {isHovered && (
          <div>
            {Object.keys(disabledLayers).map((layerName) => (
              <FormGroup key={layerName}>
                <FormControlLabel
                  control={
                    <Checkbox
                      sx={{ padding: 1.5 }}
                      size="small"
                      checked={!disabledLayers[layerName]}
                      onChange={() => {
                        const updatedLayers = { ...disabledLayers };
                        updatedLayers[layerName] = !updatedLayers[layerName];
                        AppEvents.disabledLayers.next(updatedLayers);
                      }}
                    />
                  }
                  label={layerName}
                  sx={{ margin: '0' }}
                />
              </FormGroup>
            ))}
          </div>
        )}
      </div>
    </Box>
  );
};
