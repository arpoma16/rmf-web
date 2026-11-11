import { Html, Text } from '@react-three/drei';
import { MeshProps, ThreeEvent, useLoader } from '@react-three/fiber';
import React from 'react';
import { Color, Euler, Texture, TextureLoader, Vector3 } from 'three';

import { CircleShape } from './circle-shape';
import { debounce } from './shape-three-rendering';
import { TextThreeRendering } from './text-maker';

export interface RobotData {
  fleet: string;
  name: string;
  model: string;
  footprint: number;
  scale: number;
  color: string;
  inConflict?: boolean;
  iconPath?: string;
}

interface RobotThreeMakerProps {
  imageUrl?: string;
  robot: RobotData;
  position: Vector3;
  onRobotClick?: (ev: ThreeEvent<MouseEvent>, robot: RobotData) => void;
  rotation: Euler;
  circleSegment: number;
  fontPath?: string;
  robotLabel: boolean;
  /** Persistent highlight (ring + label) of the robot that is being watched. */
  selected?: boolean;
}

const SELECTED_RING_INNER = 1.0;
const SELECTED_RING_OUTER = 1.3;
const SELECTED_COLOR = '#F5A524';

/** Ring around the robot and its name, drawn above the robot so it is not hidden by it. */
export const SelectedRobotMark = ({
  position,
  name,
  fontPath,
  showLabel,
}: {
  position: Vector3;
  name: string;
  fontPath?: string;
  showLabel: boolean;
}) => (
  <group name="selected-robot-mark">
    <mesh position={[position.x, position.y, position.z + 0.5]}>
      <ringGeometry args={[SELECTED_RING_INNER, SELECTED_RING_OUTER, 48]} />
      <meshBasicMaterial color={SELECTED_COLOR} toneMapped={false} />
    </mesh>
    {showLabel && fontPath && (
      <Text
        color={SELECTED_COLOR}
        outlineWidth={0.05}
        outlineColor="black"
        font={fontPath}
        fontSize={0.6}
        position={[position.x, position.y + SELECTED_RING_OUTER + 0.5, position.z + 0.5]}
      >
        {name}
      </Text>
    )}
  </group>
);

interface RobotImageMakerProps extends MeshProps {
  imageUrl: string;
  robot: RobotData;
  position: Vector3;
  onRobotClick?: (ev: ThreeEvent<MouseEvent>, robot: RobotData) => void;
  rotation: Euler;
}

const RobotImageMaker = ({
  imageUrl,
  position,
  rotation,
  onRobotClick,
  robot,
  ...otherProps
}: RobotImageMakerProps): JSX.Element => {
  const alphaTestThreshold = 0.5;
  const texture: Texture | undefined = useLoader(TextureLoader, imageUrl, undefined, (err) => {
    console.error(`Error loading image from ${imageUrl}:`, err);
  });

  if (!texture) {
    console.error(`Failed to create image texture with ${robot.iconPath}.`);
    return <></>;
  }

  return (
    <>
      <mesh
        position={position}
        rotation={new Euler(0, 0, rotation.z)}
        onClick={(ev: ThreeEvent<MouseEvent>) => onRobotClick && onRobotClick(ev, robot)}
        {...otherProps}
      >
        <planeGeometry
          attach="geometry"
          args={[texture.image.width * robot.scale, texture.image.height * robot.scale]}
        />
        <meshBasicMaterial
          attach="material"
          map={texture}
          color={new Color(robot.color)}
          alphaTest={alphaTestThreshold}
          toneMapped={false}
        />
      </mesh>
    </>
  );
};

export const RobotThreeMaker = ({
  imageUrl,
  robot,
  position,
  onRobotClick,
  rotation,
  circleSegment,
  fontPath,
  robotLabel,
  selected = false,
}: RobotThreeMakerProps): JSX.Element => {
  const [isHovered, setIsHovered] = React.useState(false);

  const debouncedHandlePointerOver = debounce(() => {
    setIsHovered(true);
  }, 300);

  const debouncedHandlePointerOut = debounce(() => {
    setIsHovered(false);
  }, 300);

  const scaleFactor = isHovered ? 2 : 1.0;

  return (
    <>
      {selected && (
        <SelectedRobotMark
          position={position}
          name={robot.name}
          fontPath={fontPath}
          // the normal label already shows the name when that layer is on
          showLabel={!robotLabel}
        />
      )}
      {isHovered && (
        <mesh position={position} scale={[0.5, 0.5, 0.5]}>
          <Html zIndexRange={[1]}>
            <div
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.8)',
                padding: '0.2rem 0.5rem',
                borderRadius: '4px',
                fontSize: '0.6rem',
                transform: `scale(${scaleFactor})`,
                transition: 'transform 0.3s',
              }}
            >
              {robot.name}
            </div>
          </Html>
        </mesh>
      )}
      {robotLabel && fontPath && fontPath.length > 0 ? (
        <Text color="black" font={fontPath} fontSize={0.5} position={position}>
          {robot.name}
        </Text>
      ) : robotLabel ? (
        <TextThreeRendering position={[position.x, position.y, 1]} text={robot.name} />
      ) : null}
      {imageUrl ? (
        <RobotImageMaker
          imageUrl={imageUrl}
          position={position}
          rotation={rotation}
          onRobotClick={(ev: ThreeEvent<MouseEvent>) => onRobotClick && onRobotClick(ev, robot)}
          robot={robot}
          onPointerOver={debouncedHandlePointerOver}
          onPointerOut={debouncedHandlePointerOut}
        />
      ) : (
        <CircleShape
          position={position}
          rotation={rotation}
          onRobotClick={(ev: ThreeEvent<MouseEvent>) => onRobotClick && onRobotClick(ev, robot)}
          robot={robot}
          segment={circleSegment}
          onPointerOver={debouncedHandlePointerOver}
          onPointerOut={debouncedHandlePointerOut}
        />
      )}
    </>
  );
};
