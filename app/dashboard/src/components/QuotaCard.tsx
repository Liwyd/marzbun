import {
  Box,
  Card,
  chakra,
  HStack,
  Progress,
  Text,
  Tooltip,
} from "@chakra-ui/react";
import { CircleStackIcon } from "@heroicons/react/24/outline";
import { FC } from "react";
import { useTranslation } from "react-i18next";
import { formatBytes } from "utils/formatByte";

const QuotaIcon = chakra(CircleStackIcon, {
  baseStyle: { w: 5, h: 5, position: "relative", zIndex: "2" },
});

type QuotaCardProps = {
  allocated: number;       // bytes
  quotaLimit: number;      // bytes (always > 0 when this component is shown)
};

function usageColor(pct: number): string {
  if (pct >= 100) return "red";
  if (pct >= 90) return "orange";
  if (pct >= 70) return "yellow";
  return "primary";
}

export const QuotaCard: FC<QuotaCardProps> = ({ allocated, quotaLimit }) => {
  const { t } = useTranslation();
  const remaining = Math.max(0, quotaLimit - allocated);
  const pct = quotaLimit > 0 ? Math.min(100, (allocated / quotaLimit) * 100) : 0;
  const color = usageColor(pct);

  return (
    <Card
      p={6}
      borderWidth="1px"
      borderColor={pct >= 90 ? `${color}.300` : "light-border"}
      bg="#F9FAFB"
      _dark={{ borderColor: pct >= 90 ? `${color}.600` : "gray.600", bg: "gray.750" }}
      borderStyle="solid"
      boxShadow="none"
      borderRadius="12px"
      width="full"
      display="flex"
      flexDirection="column"
      gap={3}
    >
      <HStack justifyContent="space-between" alignItems="center">
        <HStack alignItems="center" columnGap="4">
          <Box
            p="2"
            position="relative"
            color="white"
            _before={{
              content: `""`,
              position: "absolute",
              top: 0, left: 0,
              bg: `${color}.400`,
              display: "block",
              w: "full", h: "full",
              borderRadius: "5px",
              opacity: ".5",
              z: "1",
            }}
            _after={{
              content: `""`,
              position: "absolute",
              top: "-5px", left: "-5px",
              bg: `${color}.400`,
              display: "block",
              w: "calc(100% + 10px)", h: "calc(100% + 10px)",
              borderRadius: "8px",
              opacity: ".4",
              z: "1",
            }}
          >
            <QuotaIcon />
          </Box>
          <Text
            color="gray.600"
            _dark={{ color: "gray.300" }}
            fontWeight="medium"
            textTransform="capitalize"
            fontSize="sm"
          >
            {t("quota.allocatedCapacity", "Allocated Capacity")}
          </Text>
        </HStack>
        <Tooltip
          label={`${formatBytes(allocated)} / ${formatBytes(quotaLimit)}`}
          placement="top"
        >
          <Box fontSize="lg" fontWeight="semibold" color={`${color}.500`} cursor="default">
            {pct.toFixed(1)}%
          </Box>
        </Tooltip>
      </HStack>

      <Box>
        <Progress
          value={pct}
          colorScheme={color}
          size="sm"
          borderRadius="full"
          bg="gray.200"
          _dark={{ bg: "gray.600" }}
        />
        <HStack justifyContent="space-between" mt={1}>
          <Text fontSize="xs" color="gray.500">
            {formatBytes(allocated)} {t("quota.used", "used")}
          </Text>
          <Text fontSize="xs" color={remaining === 0 ? "red.500" : "gray.500"}>
            {formatBytes(remaining)} {t("quota.remaining", "remaining")}
          </Text>
        </HStack>
      </Box>
    </Card>
  );
};
