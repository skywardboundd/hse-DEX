# export function createJettonVaultSwapRequest(
#     destinationVault: Address,
#     minAmountOut: bigint = 0n,
#     timeout: bigint = 0n,
#     payloadOnSuccess: Cell | null = null,
#     payloadOnFailure: Cell | null = null,
# ) {
#     const swapRequest: SwapRequest = {
#         $$type: "SwapRequest",
#         destinationVault: destinationVault,
#         minAmountOut: minAmountOut,
#         timeout: timeout,
#         payloadOnSuccess: payloadOnSuccess,
#         payloadOnFailure: payloadOnFailure,
#     }

#     return createJettonVaultMessage(
#         SwapRequestOpcode,
#         beginCell().store(storeSwapRequest(swapRequest)).endCell(),
#         // This function does not specify proof code and data as there is no sense to swap anything without ever providing a liquidity.
#         undefined,
#         undefined,
#     )
# }


# export function storeSwapRequest(src: SwapRequest) {
#     return (builder: Builder) => {
#         const b_0 = builder;
#         b_0.storeAddress(src.destinationVault);
#         b_0.storeUint(src.minAmountOut, 256);
#         b_0.storeUint(src.timeout, 32);
#     };
# }

# export const SwapRequestOpcode = 3215360001n;
# export const VaultDepositOpcode = 1690340348n;
# export const TakeWalletAddressOpcode = 3513996288n;
# export const gasForBurn = 6700n;
# export const gasForTransfer = 10500n;
# export const minTonsForStorage = 10000000n;
# export const Basechain = 0n;

SwapRequestOpcode = 3215360001
VaultDepositOpcode = 1690340348
TakeWalletAddressOpcode = 3513996288
gasForBurn = 6700
gasForTransfer = 10500
minTonsForStorage = 10000000
Basechain = 0

from pytoniq import begin_cell, Cell, Address

def createJettonVaultMessage(self, opcode: int, payload: Cell, proofCode: Cell | None, proofData: Cell | None):
    return begin_cell().store_uint(0, 1).store_maybe_ref(proofCode).store_maybe_ref(proofData).store_uint(opcode, 32).store_ref(payload).end_cell()


def createJettonVaultSwapRequest(destinationVault: Address, minAmountOut: int = 0, timeout: int = 0, payloadOnSuccess: Cell | None = None, payloadOnFailure: Cell | None = None):
    swapRequest = begin_cell().store_address(destinationVault).store_uint(minAmountOut, 256).store_uint(timeout, 32).end_cell()
    return createJettonVaultMessage(SwapRequestOpcode, swapRequest, None, None)


# export function createJettonVaultLiquidityDepositPayload(
#     LPContract: Address,
#     proofCode: Cell | undefined,
#     proofData: Cell | undefined,
#     minAmountToDeposit: bigint = 0n,
#     lpTimeout: bigint = BigInt(Math.ceil(Date.now() / 1000) + 5 * 60), // 5 minutes
#     payloadOnSuccess: Cell | null = null,
#     payloadOnFailure: Cell | null = null,
# ) {
#     return createJettonVaultMessage(
#         LPDepositPartOpcode,
#         beginCell()
#             .store(
#                 storeLPDepositPart({
#                     $$type: "LPDepositPart",
#                     liquidityDepositContract: LPContract,
#                     additionalParams: {
#                         $$type: "AdditionalParams",
#                         minAmountToDeposit: minAmountToDeposit,
#                         lpTimeout: lpTimeout,
#                         payloadOnSuccess: payloadOnSuccess,
#                         payloadOnFailure: payloadOnFailure,
#                     },
#                 }),
#             )
#             .endCell(),
#         proofCode,
#         proofData,
#     )
# }

# export function storeLPDepositPart(src: LPDepositPart) {
#     return (builder: Builder) => {
#         const b_0 = builder;
#         b_0.storeAddress(src.liquidityDepositContract);
#         b_0.store(storeAdditionalParams(src.additionalParams));
#     };
# }

def createJettonVaultLiquidityDepositPayload(LPContract: Address, proofCode: Cell | None, proofData: Cell | None, minAmountToDeposit: int = 0, lpTimeout: int = 0, payloadOnSuccess: Cell | None = None, payloadOnFailure: Cell | None = None):
    liquidityDepositPart = begin_cell().store_address(LPContract).store_address(proofCode).store_address(proofData).store_uint(minAmountToDeposit, 256).store_uint(lpTimeout, 32).end_cell()
    return createJettonVaultMessage(VaultDepositOpcode, liquidityDepositPart, proofCode, proofData)